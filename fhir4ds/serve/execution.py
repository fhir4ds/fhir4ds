"""Execution pipeline shared by the SQL-on-FHIR operation routes.

Each operation route is a thin wrapper: resolve the Library/ViewDefinition
(from the path, from ``queryReference``/``viewReference``, or from
``queryResource``/``viewResource``), then hand the work to this module, which
owns the part that must behave identically everywhere:

1. validate the request ``Parameters`` against the operation's declaration;
2. resolve the output format (``_format`` beats ``Accept``);
3. apply the server row cap to ``_limit``;
4. run the capability under the connection lock;
5. turn diagnostics into an ``OperationOutcome`` or the result into bytes.

Parameter values never touch SQL text: they are decoded here into plain Python
values and bound by the SQLQuery runner's prepared statements.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from starlette.responses import Response

from fhir4ds.operations.capabilities.sqlquery import sqlquery_run
from fhir4ds.operations.capabilities.tabular import TabularResult
from fhir4ds.operations.capabilities.viewdefinition_run import viewdefinition_run

from . import formats, sources
from .config import ServeContext
from .errors import bad_request, from_diagnostics
from .parameters import ParametersBag, ParameterSpec

# -- operation parameter declarations (IG tables) ---------------------------

FORMAT_PARAMETER = ParameterSpec(
    "_format",
    "code",
    documentation="Output format: json, ndjson, csv, parquet, fhir. Defaults to ndjson.",
)
HEADER_PARAMETER = ParameterSpec(
    "header", "boolean", documentation="Include CSV headers (default true). CSV only."
)
LIMIT_PARAMETER = ParameterSpec(
    "_limit",
    "integer",
    documentation="Maximum number of rows to return, applied after evaluation.",
)
SOURCE_PARAMETER = ParameterSpec(
    "source", "string", documentation="Named external data source for the ViewDefinition tables."
)

QUERY_REFERENCE_PARAMETER = ParameterSpec(
    "queryReference", "reference", documentation="Reference to a SQLQuery Library stored here."
)
QUERY_RESOURCE_PARAMETER = ParameterSpec(
    "queryResource", "resource", documentation="Inline SQLQuery Library to execute."
)
PARAMETERS_PARAMETER = ParameterSpec(
    "parameters",
    "parameters",
    documentation="Input parameters bound by name to the Library's declared parameters.",
)

VIEW_REFERENCE_PARAMETER = ParameterSpec(
    "viewReference", "reference", documentation="Reference to a ViewDefinition stored here."
)
VIEW_RESOURCE_PARAMETER = ParameterSpec(
    "viewResource", "resource", documentation="Inline ViewDefinition to execute."
)

SQLQUERY_RUN_PARAMETERS: tuple[ParameterSpec, ...] = (
    FORMAT_PARAMETER,
    HEADER_PARAMETER,
    QUERY_REFERENCE_PARAMETER,
    QUERY_RESOURCE_PARAMETER,
    PARAMETERS_PARAMETER,
    SOURCE_PARAMETER,
    LIMIT_PARAMETER,
)

#: Parameters declared by the IG's $viewdefinition-run that this phase does not
#: implement are declared ``supported=False`` so the server answers with the
#: IG's 400 ``not-supported`` instead of silently ignoring them.
VIEWDEFINITION_RUN_PARAMETERS: tuple[ParameterSpec, ...] = (
    FORMAT_PARAMETER,
    HEADER_PARAMETER,
    VIEW_REFERENCE_PARAMETER,
    VIEW_RESOURCE_PARAMETER,
    ParameterSpec("patient", "reference", supported=False),
    ParameterSpec("group", "reference", supported=False),
    SOURCE_PARAMETER,
    ParameterSpec("resource", "resource", supported=False),
    LIMIT_PARAMETER,
    ParameterSpec("_since", "instant", supported=False),
)

#: FHIR primitive ``value[x]`` elements accepted inside a nested ``parameters``
#: resource, with the Python value the SQLQuery runner binds.
_PARAMETER_VALUE_TYPES: Mapping[str, Callable[[Any], Any]] = {
    "valueString": str,
    "valueCode": str,
    "valueMarkdown": str,
    "valueId": str,
    "valueUri": str,
    "valueUrl": str,
    "valueCanonical": str,
    "valueUuid": str,
    "valueOid": str,
    "valueBase64Binary": str,
    "valueDate": str,
    "valueDateTime": str,
    "valueTime": str,
    "valueInstant": str,
    "valueDecimal": float,
    "valueBoolean": bool,
    "valueInteger": int,
    "valuePositiveInt": int,
    "valueUnsignedInt": int,
    # FHIR integer64 travels as a JSON string.
    "valueInteger64": int,
}


# -- request shaping --------------------------------------------------------


def resolve_source_table(context: ServeContext, bag: ParametersBag) -> str:
    """Map the ``source`` parameter onto a physical table.

    Configured names, paths under ``ServeConfig.data_root``, and dataset URIs are
    all handled by :mod:`fhir4ds.serve.sources`; this wrapper only extracts the
    parameter so every operation route resolves it the same way.
    """
    source = bag.text(SOURCE_PARAMETER)
    if source is None:
        return context.config.source_table
    return sources.resolve_source_table(context, source)


def nested_parameters(bag: ParametersBag) -> dict[str, Any]:
    """Decode the nested ``parameters`` resource into name → Python value."""
    resource = bag.value(PARAMETERS_PARAMETER)
    if resource is None:
        return {}
    if resource.get("resourceType") != "Parameters":
        raise bad_request(
            "The parameters parameter must be a FHIR Parameters resource; got "
            f"resourceType {resource.get('resourceType')!r}",
            expression=["parameters"],
            code="structure",
        )
    entries = resource.get("parameter")
    if entries is None:
        return {}
    if not isinstance(entries, list):
        raise bad_request(
            "parameters.parameter must be an array",
            expression=["parameters"],
            code="structure",
        )

    values: dict[str, Any] = {}
    for index, entry in enumerate(entries):
        where = ["parameters", f"parameter[{index}]"]
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise bad_request(
                "parameters.parameter entries require a name",
                expression=where,
                code="structure",
            )
        name = entry["name"]
        value_fields = [key for key in entry if key.startswith("value")]
        if not value_fields:
            raise bad_request(
                f"Parameter {name!r} inside parameters supplies no value[x]",
                expression=where,
                code="value",
            )
        if len(value_fields) > 1:
            raise bad_request(
                f"Parameter {name!r} inside parameters supplies multiple value[x] "
                f"elements ({', '.join(sorted(value_fields))})",
                expression=where,
                code="value",
            )
        field = value_fields[0]
        decoder = _PARAMETER_VALUE_TYPES.get(field)
        if decoder is None:
            raise bad_request(
                f"Parameter {name!r} inside parameters uses {field}, which is not a "
                f"supported SQLQuery parameter value type",
                expression=where,
                code="not-supported",
            )
        raw = entry[field]
        if raw is None:
            raise bad_request(
                f"Parameter {name!r} inside parameters has a null value", expression=where
            )
        try:
            values[name] = decoder(raw)
        except (TypeError, ValueError):
            raise bad_request(
                f"Parameter {name!r} inside parameters has an invalid {field} value: {raw!r}",
                expression=where,
                code="value",
            ) from None
    return values


def validate_declared_parameter_names(library: Any, supplied: Mapping[str, Any]) -> None:
    """Reject parameter names the Library does not declare.

    The engine deliberately ignores extra parameters; a spelling mistake would
    silently produce a query missing its filter, so the HTTP surface rejects it
    with the IG's 400 instead.
    """
    declared = _declared_parameter_names(library)
    if declared is None:
        return
    unknown = sorted(set(supplied) - declared)
    if unknown:
        raise bad_request(
            f"Unknown parameter name(s) {', '.join(unknown)}. "
            f"This Library declares: {', '.join(sorted(declared)) or 'none'}",
            expression=unknown,
        )


def _declared_parameter_names(library: Any) -> set[str] | None:
    if not isinstance(library, dict):
        parameter = getattr(library, "parameter", None)
        if parameter is None:
            return None
        return {entry.name for entry in parameter if getattr(entry, "name", None)}
    parameter = library.get("parameter")
    if parameter is None:
        return set()
    if not isinstance(parameter, list):
        return None
    names = set()
    for entry in parameter:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.add(entry["name"])
    return names


# -- execution --------------------------------------------------------------


def execute_operation(
    context: ServeContext,
    bag: ParametersBag,
    *,
    parameter_specs: tuple[ParameterSpec, ...],
    run: Callable[[str, int | None], TabularResult],
    accept: str | None = None,
) -> Response:
    """Validate, execute, and serialize one operation invocation."""
    bag.validate(parameter_specs)
    # Format first: an unsupported _format is a 400 and must not run SQL.
    output_format = formats.negotiate_format(bag.code(FORMAT_PARAMETER), accept)
    header = bag.boolean(HEADER_PARAMETER)
    limit = context.config.capped_limit(bag.integer(LIMIT_PARAMETER))
    source_table = resolve_source_table(context, bag)

    result = context.run_locked(run, source_table, limit)

    if not result.ok:
        raise from_diagnostics(result.diagnostics)

    body, content_type = formats.serialize(
        result, output_format, header=True if header is None else header
    )
    return Response(content=body, media_type=content_type)


def sqlquery_operation(
    context: ServeContext,
    bag: ParametersBag,
    *,
    library: Any,
    accept: str | None = None,
) -> Response:
    """Run ``$sqlquery-run`` for one already-resolved Library."""
    values = nested_parameters(bag)
    validate_declared_parameter_names(library, values)
    resolver = context.store.resolver()

    def run(source_table: str, limit: int | None) -> TabularResult:
        return sqlquery_run(
            library,
            connection=context.connection,
            resolver=resolver,
            parameters=values,
            source_table=source_table,
            limit=limit,
        )

    return execute_operation(
        context, bag, parameter_specs=SQLQUERY_RUN_PARAMETERS, run=run, accept=accept
    )


def viewdefinition_operation(
    context: ServeContext,
    bag: ParametersBag,
    *,
    view_definition: Any,
    accept: str | None = None,
) -> Response:
    """Run ``$viewdefinition-run`` / ``$run`` for one resolved ViewDefinition."""

    def run(source_table: str, limit: int | None) -> TabularResult:
        return viewdefinition_run(
            view_definition,
            connection=context.connection,
            source_table=source_table,
            limit=limit,
        )

    return execute_operation(
        context, bag, parameter_specs=VIEWDEFINITION_RUN_PARAMETERS, run=run, accept=accept
    )


__all__ = [
    "SQLQUERY_RUN_PARAMETERS",
    "VIEWDEFINITION_RUN_PARAMETERS",
    "QUERY_REFERENCE_PARAMETER",
    "QUERY_RESOURCE_PARAMETER",
    "VIEW_REFERENCE_PARAMETER",
    "VIEW_RESOURCE_PARAMETER",
    "execute_operation",
    "sqlquery_operation",
    "viewdefinition_operation",
    "nested_parameters",
    "resolve_source_table",
    "validate_declared_parameter_names",
]
