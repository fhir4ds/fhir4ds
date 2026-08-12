"""Dataclasses for the SQL-on-FHIR v2 Analytics Layer (SQLQuery / SQLView).

The spec defines two Library profiles:
  * ``SQLQuery``  — https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery
  * ``SQLView``   — https://sql-on-fhir.org/StructureDefinition/SQLView

Both share the same structural shape; the only difference is that
``parameter`` is ``0..0`` on SQLView. The dataclasses below intentionally
mirror the FSH profile shape so parser and validator can stay close to
the spec text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Canonical profile URLs (reserved by the spec).
SQLQUERY_PROFILE_CANONICAL = "https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery"
SQLVIEW_PROFILE_CANONICAL = "https://sql-on-fhir.org/ig/StructureDefinition/SQLView"

# Library type code defined by the spec.
SQLQUERY_LIBRARY_TYPE_CODE = "sql-query"

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
