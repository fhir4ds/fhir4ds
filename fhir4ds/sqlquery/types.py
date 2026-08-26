"""Dataclasses for the SQL-on-FHIR v2 Analytics Layer (SQLQuery / SQLView).

The spec defines two Library profiles:
  * ``SQLQuery``  — http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/SQLQuery
  * ``SQLView``   — http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/SQLView

Both share the same structural shape; the only difference is that
``parameter`` is ``0..0`` on SQLView. The dataclasses below intentionally
mirror the FSH profile shape so parser and validator can stay close to
the spec text.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Canonical profile URLs (engine-legacy spellings retained for backwards
# compatibility with libraries authored against earlier releases).
SQLQUERY_PROFILE_CANONICAL = "https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery"
SQLVIEW_PROFILE_CANONICAL = "https://sql-on-fhir.org/ig/StructureDefinition/SQLView"

# Every published form of the SQLQuery/SQLView profile StructureDefinitions
# (sql-on-fhir-v2 input/fsh/profiles/library-profiles.fsh, IG canonical
# http://hl7.org/fhir/uv/sql-on-fhir per sushi-config.yaml) uses the
# hl7.org/fhir/uv/sql-on-fhir base. The sql-on-fhir.org/ig spellings above
# (and the legacy non-/ig SQLView form) are retained for backwards
# compatibility. Profile recognition accepts ALL forms below; official IG
# examples declare the hl7.org/fhir/uv form.
SQLQUERY_PROFILE_CANONICALS = frozenset({
    SQLQUERY_PROFILE_CANONICAL,
    "http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/SQLQuery",
    "https://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/SQLQuery",
})
SQLVIEW_PROFILE_CANONICALS = frozenset({
    SQLVIEW_PROFILE_CANONICAL,
    "https://sql-on-fhir.org/StructureDefinition/SQLView",  # legacy form
    "http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/SQLView",
    "https://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/SQLView",
})

# Library type codes defined by the spec (CodeSystem LibraryTypesCodes).
SQLQUERY_LIBRARY_TYPE_CODE = "sql-query"
SQLVIEW_LIBRARY_TYPE_CODE = "sql-view"

# Canonical CodeSystem URL for LibraryTypesCodes. The profiles fix
# ``type = LibraryTypesCodes#sql-query|sql-view``; a coding whose system is
# present but different is a different concept and must not satisfy the
# fixed type.
LIBRARY_TYPES_CODESYSTEM_CANONICALS = frozenset({
    "http://hl7.org/fhir/uv/sql-on-fhir/CodeSystem/LibraryTypesCodes",
    "https://hl7.org/fhir/uv/sql-on-fhir/CodeSystem/LibraryTypesCodes",
})


def matches_profile_canonical(profile: str, canonicals: "frozenset[str]") -> bool:
    """True when ``profile`` equals a canonical or pins it with a ``|version``."""
    return any(
        profile == c or profile.startswith(c + "|") for c in canonicals
    )

# Content-type prefix required by the sql-must-be-sql-expressions invariant.
SQL_CONTENT_TYPE_PREFIX = "application/sql"

# Supported DuckDB dialects, in preference order (most-specific first).
# Authors targeting other dialects receive UnsupportedDialectError.
SUPPORTED_CONTENT_TYPES: tuple[str, ...] = (
    "application/sql;dialect=duckdb",
    "application/sql",
)


@dataclass
class SQLContent:
    """A single ``content[]`` entry on a SQLQuery/SQLView Library.

    Attributes:
        content_type: The ``content.contentType`` string. Must start with
            ``application/sql`` per the ``sql-must-be-sql-expressions``
            invariant.
        data: The base64-decoded SQL body. The parser decodes the raw
            base64 ``content.data`` into a ``str``; downstream code never
            sees encoded bytes.
        sql_text: Optional ``content.extension[sqlText]`` plain-text
            rendering for readability. Not used by the runner.
    """

    content_type: str
    data: str
    sql_text: Optional[str] = None
    # Verbatim preservation of the remaining Attachment keys (e.g.
    # ``extension`` incl. sqlText, ``language``, ``url``, ``title``) for
    # roundtrip fidelity.
    extra_fields: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_supported_dialect(self) -> bool:
        """True when ``content_type`` matches one of the supported DuckDB dialects."""
        return self.content_type in SUPPORTED_CONTENT_TYPES


@dataclass
class SQLRelatedArtifact:
    """A ``relatedArtifact`` dependency declaration.

    Each relatedArtifact ties a table alias (``label``) used inside the raw
    SQL body to a ViewDefinition or SQLView canonical URL (``resource``).
    The runner materializes each dependency as a DuckDB view named after
    ``label`` so the raw SQL resolves the alias correctly.

    Attributes:
        label: The table alias used inside the SQL body. Must satisfy
            ``sql-name``.
        resource: Canonical URL of the ViewDefinition or SQLView being
            referenced.
        resource_type: ``"ViewDefinition"`` or ``"SQLView"``. The parser
            infers this from the canonical or leaves it as ``None`` for
            the runner to resolve.
    """

    label: str
    resource: str
    resource_type: Optional[str] = None
    # Verbatim preservation of the remaining RelatedArtifact keys (e.g.
    # ``display``, ``document``, ``extension``) for roundtrip fidelity.
    extra_fields: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass
class SQLParameter:
    """A ``parameter`` definition on a SQLQuery Library.

    SQLView forbids parameters (``parameter 0..0`` per profile).

    Attributes:
        name: Parameter name. Used as the DuckDB named-parameter key.
        type: FHIR primitive type name. Coerced via
            :func:`fhir4ds.viewdef.types.fhir_type_to_duckdb` at bind time.
        use: Always ``"in"`` per the profile. Included for completeness.
    """

    name: str
    type: str
    use: str = "in"
    # Verbatim preservation of the remaining Parameter keys (e.g.
    # ``documentation``, ``min``, ``max``, ``extension``) for roundtrip
    # fidelity.
    extra_fields: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass
class _SQLLibraryBase:
    """Shared fields between SQLQuery and SQLView."""

    id: Optional[str] = None
    url: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    content: List[SQLContent] = field(default_factory=list)
    related_artifact: List[SQLRelatedArtifact] = field(default_factory=list)
    # Raw Library JSON preserved verbatim for roundtrip (mirrors the
    # ``ViewDefinition.extra_fields`` bag at §G-3). ``repr=False`` and
    # ``compare=False`` keep the bag out of repr and equality semantics.
    extra_fields: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
    # Verbatim ``meta`` of the source Library (tags, security, versionId,
    # source profile declarations) preserved for roundtrip fidelity.
    meta: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
    # Verbatim ``type`` CodeableConcept (system, display, text, extra
    # codings) preserved for roundtrip fidelity.
    type_concept: Optional[Dict[str, Any]] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize back to a FHIR Library JSON dict.

        Roundtrips :func:`fhir4ds.sqlquery.parser.parse_library`: unmodeled
        Library keys preserved verbatim via ``extra_fields`` (and per-entry
        ``extra_fields`` bags on content/relatedArtifact/parameter),
        ``content[].data`` re-encoded as base64, and the source ``meta`` /
        ``type`` preserved verbatim. ``meta.profile`` is only augmented with
        the dataclass's profile canonical when no recognized profile
        declaration is already present — the originally-declared canonical
        (official or legacy) is never rewritten.
        """
        out: Dict[str, Any] = {"resourceType": "Library"}
        if self.id is not None:
            out["id"] = self.id
        # meta: verbatim, with the profile canonical added only when absent.
        meta: Dict[str, Any] = dict(self.meta) if self.meta else {}
        raw_profiles = meta.get("profile")
        profiles = (
            [p for p in raw_profiles if isinstance(p, str)]
            if isinstance(raw_profiles, list) else []
        )
        canonicals = (
            SQLQUERY_PROFILE_CANONICALS
            if isinstance(self, SQLQuery)
            else SQLVIEW_PROFILE_CANONICALS
        )
        if not any(matches_profile_canonical(p, canonicals) for p in profiles):
            profiles = profiles + [self.profile_canonical]
        meta["profile"] = profiles
        out["meta"] = meta
        type_code = (
            SQLQUERY_LIBRARY_TYPE_CODE
            if isinstance(self, SQLQuery)
            else SQLVIEW_LIBRARY_TYPE_CODE
        )
        if isinstance(self.type_concept, dict):
            out["type"] = dict(self.type_concept)
        else:
            out["type"] = {"coding": [{"code": type_code}]}
        for key in ("url", "name", "version", "title", "status"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        out["content"] = []
        for c in self.content:
            entry: Dict[str, Any] = dict(c.extra_fields)
            entry["contentType"] = c.content_type
            entry["data"] = base64.b64encode(c.data.encode("utf-8")).decode("ascii")
            out["content"].append(entry)
        if self.related_artifact:
            out["relatedArtifact"] = []
            for ra in self.related_artifact:
                ra_entry: Dict[str, Any] = dict(ra.extra_fields)
                ra_entry.update(
                    {"type": "depends-on", "label": ra.label, "resource": ra.resource}
                )
                out["relatedArtifact"].append(ra_entry)
        parameters = getattr(self, "parameter", None)
        if parameters:
            out["parameter"] = []
            for p in parameters:
                p_entry: Dict[str, Any] = dict(p.extra_fields)
                p_entry.update({"name": p.name, "type": p.type, "use": p.use})
                out["parameter"].append(p_entry)
        out.update(self.extra_fields)
        return out


@dataclass
class SQLQuery(_SQLLibraryBase):
    """A Library resource conforming to the SQLQuery profile.

    Differs from :class:`SQLView` only in that ``parameter 1..*`` is
    permitted (though typical queries have at least one parameter;
    zero-parameter queries should still use SQLQuery if they might be
    wrapped by other queries that pass parameters).
    """

    parameter: List[SQLParameter] = field(default_factory=list)

    @property
    def profile_canonical(self) -> str:
        return SQLQUERY_PROFILE_CANONICAL


@dataclass
class SQLView(_SQLLibraryBase):
    """A Library resource conforming to the SQLView profile.

    A SQLView is a reusable named query referenced as a virtual table by
    other queries. Parameters are forbidden (``parameter 0..0``).
    """

    @property
    def profile_canonical(self) -> str:
        return SQLVIEW_PROFILE_CANONICAL
