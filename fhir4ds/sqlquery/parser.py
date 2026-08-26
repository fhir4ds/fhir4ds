"""Parse FHIR Library JSON resources into SQLQuery / SQLView dataclasses.

Profile-conformant parser for the SQL-on-FHIR v2 Analytics Layer.
Consumes a FHIR ``Library`` JSON dict (or JSON string), inspects
``meta.profile`` to dispatch between SQLQuery and SQLView, validates
the structural invariants, and returns a typed dataclass.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional, Union

from .errors import SQLQueryParseError
from .types import (
    LIBRARY_TYPES_CODESYSTEM_CANONICALS,
    SQLQUERY_LIBRARY_TYPE_CODE,
    SQLQUERY_PROFILE_CANONICALS,
    SQLVIEW_LIBRARY_TYPE_CODE,
    SQLVIEW_PROFILE_CANONICALS,
    SQLContent,
    SQLParameter,
    SQLQuery,
    SQLRelatedArtifact,
    SQLView,
    matches_profile_canonical,
)
from .validator import validate_sql_library


# Top-level Library keys emitted by ``to_dict`` from dataclass fields.
# Every other key (known FHIR fields like ``description`` / ``publisher``
# as well as unknown/custom keys) flows into the verbatim ``extra_fields``
# bag so the parse -> serialize roundtrip loses nothing.
_MODELED_LIBRARY_KEYS = frozenset({
    "resourceType", "id", "meta", "url", "version", "name", "title",
    "status", "type", "content", "relatedArtifact", "parameter",
})


def _extract_profile_urls(data: Dict[str, Any]) -> list[str]:
    meta = data.get("meta") or {}
    if not isinstance(meta, dict):
        return []
    profiles = meta.get("profile") or []
    if not isinstance(profiles, list):
        return []
    return [p for p in profiles if isinstance(p, str)]


def _detect_profile(data: Dict[str, Any]) -> str:
    """Return 'SQLQuery' or 'SQLView' based on meta.profile declaration.

    Accepts every published canonical form (official
    ``hl7.org/fhir/uv/sql-on-fhir`` base plus the engine-legacy
    ``sql-on-fhir.org`` spellings), optionally version-pinned with ``|``.

    Raises:
        SQLQueryParseError: when neither profile canonical is present, or
            both are declared (ambiguous).
    """
    profiles = _extract_profile_urls(data)
    has_query = any(matches_profile_canonical(p, SQLQUERY_PROFILE_CANONICALS) for p in profiles)
    has_view = any(matches_profile_canonical(p, SQLVIEW_PROFILE_CANONICALS) for p in profiles)
    if has_query and has_view:
        raise SQLQueryParseError(
            f"Library declares both SQLQuery and SQLView profiles; pick one. "
            f"Profiles: {profiles}"
        )
    if has_query:
        return "SQLQuery"
    if has_view:
        return "SQLView"
    raise SQLQueryParseError(
        f"Library does not declare a SQL-on-FHIR v2 Analytics Layer profile. "
        f"meta.profile must contain a SQLQuery or SQLView canonical "
        f"(e.g. 'http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/SQLQuery'). "
        f"Got: {profiles}"
    )


def _require_type_coding(data: Dict[str, Any], expected_code: str) -> None:
    """Enforce Library.type.coding contains the profile's type code.

    The SQLQuery profile fixes ``type = LibraryTypesCodes#sql-query`` and
    the SQLView profile fixes ``type = LibraryTypesCodes#sql-view``.
    """
    raw_type = data.get("type")
    if not isinstance(raw_type, dict):
        raise SQLQueryParseError(
            "Library.type must be a CodeableConcept with coding "
            f"[{expected_code!r}]"
        )
    codings = raw_type.get("coding") or []
    if not isinstance(codings, list) or not codings:
        raise SQLQueryParseError(
            "Library.type.coding must be a non-empty array"
        )
    for coding in codings:
        if not isinstance(coding, dict):
            continue
        if coding.get("code") != expected_code:
            continue
        system = coding.get("system")
        # The profiles fix the type to LibraryTypesCodes; a coding that
        # pins a *different* code system is a different concept and must
        # not satisfy the fixed type. An absent system is tolerated.
        if system is not None and system not in LIBRARY_TYPES_CODESYSTEM_CANONICALS:
            raise SQLQueryParseError(
                f"Library.type.coding code {expected_code!r} must come from the "
                f"LibraryTypesCodes code system (or omit 'system'); got system {system!r}"
            )
        return
    raise SQLQueryParseError(
        f"Library.type.coding must include code {expected_code!r}"
    )


def _parse_content(entries: Any) -> list[SQLContent]:
    if not isinstance(entries, list) or not entries:
        raise SQLQueryParseError(
            "Library.content must be a non-empty array (cardinality 1..*)"
        )
    parsed: list[SQLContent] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SQLQueryParseError(f"content[{i}] must be a JSON object")
        content_type = entry.get("contentType")
        if not isinstance(content_type, str) or not content_type:
            raise SQLQueryParseError(
                f"content[{i}].contentType must be a non-empty string"
            )
        raw_data = entry.get("data")
        if not isinstance(raw_data, str) or not raw_data:
            raise SQLQueryParseError(
                f"content[{i}].data must be a base64-encoded SQL string"
            )
        try:
            decoded = base64.b64decode(raw_data, validate=True).decode("utf-8")
        except Exception as exc:
            raise SQLQueryParseError(
                f"content[{i}].data is not valid base64-encoded UTF-8: {exc}"
            ) from exc
        sql_text: Optional[str] = None
        for ext in entry.get("extension") or []:
            if isinstance(ext, dict) and ext.get("url", "").endswith("sqlText"):
                sql_text = ext.get("valueString")
                break
        extras = {
            k: v for k, v in entry.items()
            if k not in ("contentType", "data")
        }
        parsed.append(SQLContent(
            content_type=content_type, data=decoded, sql_text=sql_text,
            extra_fields=extras,
        ))
    return parsed


def _parse_related_artifact(entries: Any) -> list[SQLRelatedArtifact]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise SQLQueryParseError("Library.relatedArtifact must be an array")
    parsed: list[SQLRelatedArtifact] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SQLQueryParseError(f"relatedArtifact[{i}] must be a JSON object")
        ra_type = entry.get("type")
        if ra_type != "depends-on":
            raise SQLQueryParseError(
                f"relatedArtifact[{i}].type must be 'depends-on' (got {ra_type!r})"
            )
        label = entry.get("label")
        if not isinstance(label, str) or not label:
            raise SQLQueryParseError(
                f"relatedArtifact[{i}].label must be a non-empty sql-name string"
            )
        resource = entry.get("resource")
        if not isinstance(resource, str) or not resource:
            raise SQLQueryParseError(
                f"relatedArtifact[{i}].resource must be a non-empty canonical"
            )
        parsed.append(SQLRelatedArtifact(
            label=label, resource=resource,
            extra_fields={
                k: v for k, v in entry.items()
                if k not in ("type", "label", "resource")
            },
        ))
    return parsed


def _parse_parameter(entries: Any) -> list[SQLParameter]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise SQLQueryParseError("Library.parameter must be an array")
    parsed: list[SQLParameter] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SQLQueryParseError(f"parameter[{i}] must be a JSON object")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise SQLQueryParseError(f"parameter[{i}].name must be a non-empty string")
        ptype = entry.get("type")
        if not isinstance(ptype, str) or not ptype:
            raise SQLQueryParseError(f"parameter[{i}].type must be a FHIR type string")
        # Library.parameter.type is bound (required) to the FHIR all-types
        # value set; the FHIR-type registry is the data-driven authority.
        from ..viewdef.types import fhir_type_to_duckdb

        try:
            fhir_type_to_duckdb(ptype)
        except ValueError as exc:
            raise SQLQueryParseError(
                f"parameter[{i}].type must be a FHIR primitive type: {exc}"
            ) from exc
        use = entry.get("use")
        if use is None:
            raise SQLQueryParseError(
                f"parameter[{i}].use is required (cardinality 1..1) and must be 'in'"
            )
        if use != "in":
            raise SQLQueryParseError(
                f"parameter[{i}].use must be 'in' (got {use!r})"
            )
        parsed.append(SQLParameter(
            name=name, type=ptype, use=use,
            extra_fields={
                k: v for k, v in entry.items()
                if k not in ("name", "type", "use")
            },
        ))
    return parsed


def _collect_extra_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve every unmodeled Library key verbatim.

    Mirrors §G-3: both known-but-unmodeled FHIR fields (``description``,
    ``publisher``, ``extension``, ...) and unknown/custom keys roundtrip
    losslessly; only the keys ``to_dict`` re-emits from dataclass fields
    are excluded.
    """
    return {
        k: v for k, v in data.items() if k not in _MODELED_LIBRARY_KEYS
    }


def parse_library(input_: Union[Dict[str, Any], str]) -> Union[SQLQuery, SQLView]:
    """Parse a FHIR Library JSON dict (or JSON string) into a typed dataclass.

    Dispatches on ``meta.profile`` to choose between :class:`SQLQuery` and
    :class:`SQLView`. Validates the result against the profile invariants
    before returning.

    Args:
        input_: A dict (already-parsed JSON) or a JSON string.

    Returns:
        A :class:`SQLQuery` or :class:`SQLView` instance.

    Raises:
        SQLQueryParseError: when the input cannot be parsed or the profile
            declaration is missing/ambiguous.
        SQLQueryValidationError: when the parsed library violates a profile
            invariant.
    """
    if isinstance(input_, str):
        try:
            data = json.loads(input_)
        except json.JSONDecodeError as exc:
            raise SQLQueryParseError(f"Library JSON is not valid: {exc}") from exc
    elif isinstance(input_, dict):
        data = input_
    else:
        raise SQLQueryParseError(
            f"parse_library expects a dict or JSON string, got {type(input_).__name__}"
        )

    if data.get("resourceType") != "Library":
        raise SQLQueryParseError(
            f"Expected resourceType='Library', got {data.get('resourceType')!r}"
        )

    profile_kind = _detect_profile(data)
    expected_type_code = (
        SQLQUERY_LIBRARY_TYPE_CODE
        if profile_kind == "SQLQuery"
        else SQLVIEW_LIBRARY_TYPE_CODE
    )
    _require_type_coding(data, expected_type_code)

    # Library.status is 1..1 on the base Library resource.
    status = data.get("status")
    if not isinstance(status, str) or not status:
        raise SQLQueryParseError(
            "Library.status is required (cardinality 1..1 on the base "
            "Library resource) and must be a non-empty string"
        )

    content = _parse_content(data.get("content"))
    related_artifact = _parse_related_artifact(data.get("relatedArtifact"))
    extensions = _collect_extra_fields(data)
    raw_meta = data.get("meta")
    meta = raw_meta if isinstance(raw_meta, dict) else {}
    raw_type = data.get("type")
    type_concept = raw_type if isinstance(raw_type, dict) else None

    common_kwargs = dict(
        id=data.get("id"),
        url=data.get("url"),
        name=data.get("name"),
        version=data.get("version"),
        title=data.get("title"),
        status=status,
        content=content,
        related_artifact=related_artifact,
        extra_fields=extensions,
        meta=meta,
        type_concept=type_concept,
    )

    if profile_kind == "SQLQuery":
        library = SQLQuery(parameter=_parse_parameter(data.get("parameter")), **common_kwargs)
    else:
        if data.get("parameter"):
            raise SQLQueryParseError(
                "SQLView profile forbids parameter (cardinality 0..0); "
                "use SQLQuery profile if parameters are needed"
            )
        library = SQLView(**common_kwargs)

    validate_sql_library(library, strict=True)
    return library


def parse_sqlquery(input_: Union[Dict[str, Any], str]) -> SQLQuery:
    """Parse a Library as a SQLQuery. Raises if the profile is SQLView."""
    result = parse_library(input_)
    if not isinstance(result, SQLQuery):
        raise SQLQueryParseError(
            f"Expected SQLQuery profile, got SQLView for {result.url or result.id!r}"
        )
    return result


def parse_sqlview(input_: Union[Dict[str, Any], str]) -> SQLView:
    """Parse a Library as a SQLView. Raises if the profile is SQLQuery."""
    result = parse_library(input_)
    if not isinstance(result, SQLView):
        raise SQLQueryParseError(
            f"Expected SQLView profile, got SQLQuery for {result.url or result.id!r}"
        )
    return result


__all__ = ["parse_library", "parse_sqlquery", "parse_sqlview"]
