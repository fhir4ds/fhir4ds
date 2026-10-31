"""``sqlquery_run`` capability: execute a SQLQuery Library.

Wraps :class:`fhir4ds.sqlquery.runner.SQLQueryRunner` and adds the two things
an HTTP/agent surface needs and the runner (correctly) does not provide:

* **column metadata** — name plus physical SQL type, captured from the DuckDB
  cursor description of the main query (via a thin recording proxy, so the
  runner itself stays untouched);
* **a typed envelope** — :class:`~fhir4ds.operations.capabilities.tabular.TabularResult`,
  carrying columns/rows on success and typed diagnostics on failure.

Parameter values reach DuckDB only through the runner's prepared statements.

Dependency resolution is delegated to a caller-supplied resolver matching
``fhir4ds.sqlquery.DependencyResolver``. A resolver signals "canonical not
found" by raising ``LookupError`` (any subclass); that is the one exception
family the capability reports as ``NOT_FOUND`` rather than an execution
error, because "the referenced ViewDefinition does not exist" is a 404 for an
HTTP surface, not a 422.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..envelopes import DiagnosticCode, Diagnostics
from .tabular import (
    ResultColumn,
    TabularResult,
    chain_contains,
    columns_from_description,
    failed,
)

#: Canonical of the operation this capability implements, per the IG.
SQLQUERY_RUN_DEFINITION = "http://sql-on-fhir.org/OperationDefinition/$sqlquery-run"

_CONTEXT = "sqlquery-run"


class _DescriptionRecordingConnection:
    """Connection proxy that remembers the last result description.

    ``SQLQueryRunner`` executes several statements per run (dependency
    ``CREATE VIEW``s, parameter ``CAST``s, then the main query) and returns
    only ``fetchall()``. The main query is always last, so recording the
    description at every ``execute`` leaves the main query's columns behind.

    Every other attribute is delegated to the wrapped connection.
    """

    __slots__ = ("_connection", "description")

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.description: tuple | None = None

    def execute(self, sql: str, parameters: Any = None) -> Any:
        if parameters is None:
            cursor = self._connection.execute(sql)
        else:
            cursor = self._connection.execute(sql, parameters)
        self.description = getattr(cursor, "description", None)
        return cursor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _diagnostic(exc: BaseException) -> Diagnostics:
    """Map a SQLQuery-layer failure to a typed diagnostic."""
    from fhir4ds.sqlquery.errors import (
        SQLQueryCycleError,
        SQLQueryMaterializationError,
        SQLQueryParseError,
        SQLQueryTypeError,
        SQLQueryValidationError,
        UnsupportedDialectError,
    )

    message = str(exc) or type(exc).__name__
    detail = type(exc).__name__

    if isinstance(exc, (SQLQueryParseError, SQLQueryValidationError)):
        code = DiagnosticCode.PARSE_ERROR
    elif isinstance(exc, SQLQueryTypeError):
        code = DiagnosticCode.INPUT_ERROR
    elif isinstance(exc, UnsupportedDialectError):
        code = DiagnosticCode.UNSUPPORTED_FEATURE
    elif isinstance(exc, (SQLQueryCycleError, SQLQueryMaterializationError)):
        # A resolver miss surfaces as a materialization failure whose cause
        # is the resolver's LookupError. Dependencies that exist but cannot be
        # materialized stay EVALUATION_ERROR.
        code = (
            DiagnosticCode.NOT_FOUND
            if chain_contains(exc, (LookupError,))
            else DiagnosticCode.EVALUATION_ERROR
        )
    else:
        code = DiagnosticCode.EVALUATION_ERROR

    return Diagnostics(code=code, message=message, detail=detail, data={"context": _CONTEXT})


def sqlquery_run(
    library: Any,
    *,
    connection: Any,
    resolver: Callable[[str], Any],
    parameters: Mapping[str, Any] | None = None,
    source_table: str = "resources",
    limit: int | None = None,
) -> TabularResult:
    """Execute a SQLQuery (or SQLView) Library and return a typed result.

    Args:
        library: A Library dict, parsed ``SQLQuery``, or parsed ``SQLView``.
        connection: DuckDB connection with the FHIRPath UDFs registered.
        resolver: Canonical → ViewDefinition/Library resolver, per
            ``fhir4ds.sqlquery.DependencyResolver``. Raises ``LookupError``
            when a canonical is unknown.
        parameters: Parameter values keyed by declared ``Library.parameter.name``.
        source_table: Physical table the materialized ViewDefinitions read.
        limit: Optional post-evaluation row cap (applied after the query ran).

    Returns:
        A :class:`TabularResult`. ``ok=False`` results carry one diagnostic and
        no rows; the exception is never re-raised.
    """
    from fhir4ds.sqlquery.runner import SQLQueryRunner

    recording = _DescriptionRecordingConnection(connection)
    try:
        runner = SQLQueryRunner(recording, resolver, source_table=source_table)
        rows = runner.execute(library, dict(parameters or {}))
    except Exception as exc:  # capability boundary: total mapping to diagnostics
        return failed(_diagnostic(exc))

    columns: tuple[ResultColumn, ...] = columns_from_description(recording.description)
    if limit is not None:
        rows = rows[: max(0, limit)]
    return TabularResult(columns=columns, rows=tuple(tuple(row) for row in rows))


__all__ = ["sqlquery_run", "SQLQUERY_RUN_DEFINITION"]
