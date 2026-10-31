"""``viewdefinition_run`` capability: evaluate one ViewDefinition.

Materializes a SQL-on-FHIR v2 ViewDefinition against the connection's
``resources`` table and returns the resulting row set as a typed envelope.

Delegates all translation to :class:`fhir4ds.viewdef.SQLGenerator` (the same
call the SQLQuery runner makes when materializing a dependency), so the HTTP
surface and the analytics layer cannot produce different SQL for the same
ViewDefinition.

FHIR-`resourceType` note: the IG publishes ViewDefinition *instances* with
``"resourceType": "ViewDefinition"``, while the engine's ``resourceType``
field means the logical model's canonical URL. The capability accepts both
spellings — the FHIR resource-type spelling is dropped before parsing — so a
resource can be served verbatim and still execute.
"""

from __future__ import annotations

from typing import Any

from ..envelopes import DiagnosticCode, Diagnostics
from .tabular import ResultColumn, TabularResult, columns_from_description, failed

#: Canonical of the operation this capability implements, per the IG.
VIEWDEFINITION_RUN_DEFINITION = (
    "http://sql-on-fhir.org/OperationDefinition/$viewdefinition-run"
)

_CONTEXT = "viewdefinition-run"

#: FHIR R4/R5 resource-type spelling for the logical model. Not the engine's
#: ``resourceType`` contract (canonical URL), so it is stripped before parsing.
FHIR_RESOURCE_TYPE_SPELLING = "ViewDefinition"


def normalize_view_definition(view_definition: Any) -> Any:
    """Drop the FHIR resource-type spelling so the engine will parse the view.

    Accepts a dict, JSON string, or parsed ViewDefinition and returns the same
    kind. Only a ``resourceType`` equal to ``"ViewDefinition"`` is removed;
    a canonical-URL ``resourceType`` (the engine's own contract) is preserved.
    """
    if isinstance(view_definition, dict):
        if view_definition.get("resourceType") == FHIR_RESOURCE_TYPE_SPELLING:
            return {
                key: value
                for key, value in view_definition.items()
                if key != "resourceType"
            }
    return view_definition


def _diagnostic(exc: BaseException) -> Diagnostics:
    """Map a ViewDefinition-layer failure to a typed diagnostic."""
    from fhir4ds.viewdef.errors import (
        ConstantResolutionError,
        GenerationError,
        ParseError,
        UnsupportedFeatureError,
        ValidationError,
    )

    message = str(exc) or type(exc).__name__
    detail = type(exc).__name__

    if isinstance(exc, ParseError):
        code = DiagnosticCode.PARSE_ERROR
    elif isinstance(exc, UnsupportedFeatureError):
        code = DiagnosticCode.UNSUPPORTED_FEATURE
    elif isinstance(exc, (ConstantResolutionError, ValidationError)):
        code = DiagnosticCode.TRANSLATION_ERROR
    elif isinstance(exc, GenerationError):
        code = DiagnosticCode.EVALUATION_ERROR
    elif isinstance(exc, LookupError):
        code = DiagnosticCode.NOT_FOUND
    else:
        code = DiagnosticCode.EVALUATION_ERROR

    return Diagnostics(code=code, message=message, detail=detail, data={"context": _CONTEXT})


def viewdefinition_run(
    view_definition: Any,
    *,
    connection: Any,
    source_table: str = "resources",
    limit: int | None = None,
) -> TabularResult:
    """Evaluate one ViewDefinition and return a typed result.

    Args:
        view_definition: A ViewDefinition dict (IG instance shape), JSON
            string, or parsed ``ViewDefinition``.
        connection: DuckDB connection with the FHIRPath UDFs registered.
        source_table: Physical table the generated SQL reads.
        limit: Optional post-evaluation row cap.

    Returns:
        A :class:`TabularResult`; failures are reported through diagnostics
        rather than raised.
    """
    from fhir4ds.viewdef.generator import SQLGenerator
    from fhir4ds.viewdef.parser import parse_view_definition

    try:
        parsed = normalize_view_definition(view_definition)
        if isinstance(parsed, (dict, str)):
            parsed = parse_view_definition(parsed)
        sql = SQLGenerator(source_table=source_table).generate(parsed)
        cursor = connection.execute(sql)
        rows = cursor.fetchall()
        columns: tuple[ResultColumn, ...] = columns_from_description(
            getattr(cursor, "description", None)
        )
    except Exception as exc:  # capability boundary: total mapping to diagnostics
        return failed(_diagnostic(exc))

    if limit is not None:
        rows = rows[: max(0, limit)]
    return TabularResult(columns=columns, rows=tuple(tuple(row) for row in rows))


__all__ = [
    "viewdefinition_run",
    "normalize_view_definition",
    "VIEWDEFINITION_RUN_DEFINITION",
    "FHIR_RESOURCE_TYPE_SPELLING",
]
