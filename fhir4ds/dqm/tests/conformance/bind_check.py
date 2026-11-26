"""FHIR4-64 — bind-only gate for generated measure SQL.

THE BLIND SPOT THIS CLOSES
--------------------------
DuckDB never binds a CTE that nothing references, and the conformance runner
projects only the POPULATION columns (``all_columns=False``).  So a measure
whose full-column SQL cannot even be planned still scored green:

    Binder Error: No function matches the given name and argument types
    'fhirpath_text(JSON[], STRING_LITERAL)'

was CMS986's ``all_columns=True`` SQL for months while ``run_dqm.py`` printed
``PASSED`` for qi-core-2025 and us-core-2025.  A whole measure can be silently
unbuildable and the gate cannot see it, because a column that no population
references is never bound (FHIR4-60 found it from the wasm lane, not from the
gate).

WHAT THIS MODULE DOES
---------------------
For one measure it translates the library exactly as the runner does — with
``all_columns=True`` so every definition column is projected and therefore
bound — and then plans the statement without evaluating it:

    EXPLAIN <generated sql>

``EXPLAIN`` runs the parser, binder and optimizer on the WHOLE statement (every
projected column, every referenced CTE) and touches no row.  It is the cheapest
honest way to answer "does this measure build at all?".

SCOPE — WHAT IT DOES **NOT** CATCH
----------------------------------
Bind-only is not execution.  The FHIR4-48 class (a scalar subquery that returns
more than one row at RUN time) is invisible here: it needs rows.  That family
stays covered by ``test_strict_scalar_subqueries_fhir4_48.py``, which executes
real fixtures on a strict connection.  This module catches the class that
needed no data at all: Binder / Catalog / Parser / Conversion errors — missing
functions, wrong signature, missing table, bad SQL shape.

SETTINGS — NOTHING IS RELAXED
-----------------------------
The connection is used as the conformance harness builds it:

* ``scalar_subquery_error_on_multiple_rows`` stays at DuckDB's DEFAULT (true).
  ``require_strict_connection()`` refuses to check a connection that masks it,
  because a masked connection would make this gate weaker than any real
  consumer (duckdb-wasm, any user connection).  Turning the rule off is how
  FHIR4-48's defect hid, so a check that silently ran masked would be part of
  the defect.
* ``max_expression_depth=10000`` is the OTHER knob the runner sets before
  executing (``runner.run_measure``); deeply nested fluent-inlined CASE chains
  legitimately exceed DuckDB's 1000-node default AT BIND TIME, so the same
  value is used here.  Omitting it would turn a passing measure into a false
  FAIL.

Data is not required: binding is a static property of the generated text plus
the table schema, so ``ensure_bind_schema()`` creates the empty ``resources`` /
``valueset_codes`` tables and the scan cost stays at zero.  That is why a
full-suite bind check is cheap compared to a scored run.
"""

from __future__ import annotations

import gc
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .config import MeasureConfig

#: DuckDB's DEFAULT for this setting. Every real consumer (duckdb-wasm in all
#: web apps, any user connection) runs with it ON.
STRICT_SETTING = "scalar_subquery_error_on_multiple_rows"

#: The runner's bind-time expression-depth budget (``runner.run_measure`` sets
#: the same value before executing). Not a relaxation — the gate uses it too.
MAX_EXPRESSION_DEPTH = 10000

#: Measurement-period fallback used when the caller supplies none. Every 2025
#: suite measure is authored against this period; the value is spliced into the
#: SQL as literals and therefore cannot affect whether the statement BINDS, so
#: a bind check may use it without reading any fixture.
DEFAULT_MEASUREMENT_PERIOD = ("2026-01-01", "2026-12-31")


class BindCheckError(RuntimeError):
    """The bind check itself could not be run honestly (premise failure).

    Distinct from a measure FAILING the check: this is "the check is not
    trustworthy", e.g. a connection that masks multi-row scalar subqueries.
    """


@dataclass(frozen=True)
class BindResult:
    """Outcome of bind-checking one measure."""

    measure_id: str
    ok: bool
    error_class: str | None = None
    error_message: str | None = None
    sql_bytes: int = 0
    sql_statements: int = 1
    translate_ms: float = 0.0
    bind_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        return self.translate_ms + self.bind_ms

    def failure_line(self) -> str:
        """One-line ``MEASURE: ExceptionClass: message`` rendering."""
        return (
            f"{self.measure_id}: {self.error_class or 'Error'}: "
            f"{self.error_message or ''}"
        )


@dataclass
class BindSummary:
    """Aggregate of a bind-check sweep."""

    results: list[BindResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def failures(self) -> list[BindResult]:
        return [r for r in self.results if not r.ok]

    @property
    def passed(self) -> int:
        return self.total - len(self.failures)

    @property
    def ok(self) -> bool:
        return not self.failures

    def headline(self) -> str:
        """``BIND OK: N/N`` on success, ``BIND FAILED: P/N`` otherwise."""
        label = "BIND OK" if self.ok else "BIND FAILED"
        return f"{label}: {self.passed}/{self.total}"

    def format_report(self, slowest: int = 5) -> str:
        """Human-readable summary: headline, failures, then the slowest measures.

        The translate/bind split is printed because they are different cost
        centres (CQL translation vs DuckDB planning) and a future pass would
        need to know which one to attack.
        """
        lines = [self.headline()]
        for result in self.failures:
            lines.append(f"  {result.failure_line()}")
        timed = sorted(self.results, key=lambda r: r.total_ms, reverse=True)
        if slowest and timed:
            shown = ", ".join(
                f"{r.measure_id} {r.total_ms / 1000:.1f}s "
                f"(translate {r.translate_ms / 1000:.1f}s + "
                f"bind {r.bind_ms / 1000:.1f}s)"
                for r in timed[:slowest]
            )
            lines.append(f"  slowest: {shown}")
        return "\n".join(lines)


def require_strict_connection(conn) -> None:
    """Refuse to run the check on a connection that masks the strict rule.

    A bind check is only meaningful if it is at least as strict as a real
    consumer. Silently checking a masked connection is the FHIR4-48 failure
    mode in a different costume.
    """
    try:
        masked = conn.execute(
            f"SELECT current_setting('{STRICT_SETTING}')"
        ).fetchone()
    except Exception as exc:  # pragma: no cover - defensive
        raise BindCheckError(
            f"cannot read '{STRICT_SETTING}' from the connection: {exc}"
        ) from exc
    if not masked or not masked[0]:
        raise BindCheckError(
            f"bind check refused: this connection has {STRICT_SETTING}=false, "
            "so it is LESS strict than every real consumer (duckdb-wasm, any "
            "user connection). Build the connection the way "
            "BenchmarkDatabase does (it SETs the default rule explicitly)."
        )


def ensure_bind_schema(conn) -> None:
    """Create the EMPTY tables generated measure SQL needs to bind.

    Binding is static: it needs the schema, never a row. Creating the tables
    empty keeps a full-suite bind check cheap and independent of whether the
    scored run's CSVs are available.

    ``fhir4ds.register()`` already creates ``valueset_codes``; ``FHIRDataLoader``
    creates ``resources`` (and the ``resolve()`` macro the SQL expects). Both
    are idempotent ``CREATE TABLE IF NOT EXISTS`` paths, so calling this on a
    connection that already has data is a no-op.
    """
    from fhir4ds.cql import FHIRDataLoader

    FHIRDataLoader(conn)


def _split_top_level_statements(sql: str) -> list[str]:
    """Split on ``;`` outside string literals and quoted identifiers.

    Generated measure SQL is single-statement, so this normally returns one
    item; it exists so a multi-statement body cannot be bound half-way and
    reported green. Both ``'`` string literals (``''`` escape) and ``"``
    quoted identifiers (``""`` escape — definition names may contain an
    apostrophe) are tracked.
    """
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote is not None:
            buffer.append(char)
            if char == quote:
                # A doubled quote is an escape inside the literal/identifier.
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    buffer.append(sql[index + 1])
                    index += 2
                    continue
                quote = None
        elif char in ("'", '"'):
            quote = char
            buffer.append(char)
        elif char == ";":
            statements.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
        index += 1
    statements.append("".join(buffer))
    return [s for s in (part.strip() for part in statements) if s]


def bind_sql(conn, sql: str) -> None:
    """Bind/plan ``sql`` without evaluating it. Raises on any plan-time error.

    ``EXPLAIN`` is used instead of a real execution because it stops after the
    optimizer: no rows are scanned, and nothing is written. DuckDB reports
    Binder / Catalog / Parser / Conversion errors here exactly as it would at
    execution.
    """
    statements = _split_top_level_statements(sql)
    if not statements:
        raise BindCheckError("refusing to bind an empty SQL statement")
    for statement in statements:
        # The statement text is the translator's output, not user input; it is
        # fed to EXPLAIN verbatim (wrapping it would change what is bound).
        conn.execute(f"EXPLAIN {statement}").fetchall()


def bind_check_sql(conn, sql: str, measure_id: str = "<inline>") -> BindResult:
    """Bind-check a SQL string that did not come from a measure translation."""
    started = time.perf_counter()
    try:
        bind_sql(conn, sql)
    except Exception as exc:  # noqa: BLE001 - every plan-time failure is a FAIL
        return BindResult(
            measure_id=measure_id,
            ok=False,
            error_class=type(exc).__name__,
            error_message=str(exc).strip(),
            sql_bytes=len(sql),
            sql_statements=len(_split_top_level_statements(sql)),
            bind_ms=(time.perf_counter() - started) * 1000,
        )
    return BindResult(
        measure_id=measure_id,
        ok=True,
        sql_bytes=len(sql),
        sql_statements=len(_split_top_level_statements(sql)),
        bind_ms=(time.perf_counter() - started) * 1000,
    )


def _all_column_names(library) -> dict[str, str]:
    """The runner's ``all_columns=True`` projection, definition for definition.

    Kept identical to ``runner.run_measure`` so the bind check binds the same
    SQL the scored run would bind when asked for all columns: every top-level
    non-``SDE`` definition becomes an output column, which is precisely what
    forces DuckDB to bind (and therefore validate) each one.
    """
    from fhir4ds.cql.parser.ast_nodes import Definition

    return {
        stmt.name: stmt.name
        for stmt in library.statements
        if isinstance(stmt, Definition) and not stmt.name.startswith("SDE")
    }


def bind_check_measure(
    conn,
    measure_config: MeasureConfig,
    *,
    all_columns: bool = True,
    strict_profiles: bool = True,
    library_cache: dict | None = None,
    parameters: dict | None = None,
    translate: Callable[..., tuple] | None = None,
) -> BindResult:
    """Translate one measure and bind (never execute) its generated SQL.

    Args:
        conn: a STRICT connection (see :func:`require_strict_connection`) with
            the ``resources`` / ``valueset_codes`` schema present. Rows are not
            required.
        measure_config: the discovered measure.
        all_columns: default True — the whole point of the gate. Every
            definition column is projected, so every CTE it needs is bound.
            A population-only projection is what let CMS986 hide.
        strict_profiles: STRICT PROFILE MODE, matching the gate's default.
        library_cache: optional in-process include-translation cache, shared
            across a sweep exactly as ``run_dqm.py`` shares it.
        parameters: measurement-period parameters for inlining. Defaults to
            ``DEFAULT_MEASUREMENT_PERIOD`` (a required parameter left unset
            makes TRANSLATION fail, which would masquerade as a bind failure).
            The value is a literal spliced into the SQL and cannot change
            whether it binds.
        translate: override for the translation step (tests inject a broken
            translation); defaults to ``runner._translate_measure``.

    Returns:
        :class:`BindResult` — ``ok=False`` with the exception class and message
        when the generated SQL cannot be planned.
    """
    from fhir4ds.cql.parser import parse_cql

    if translate is None:
        from .runner import _translate_measure as translate  # local import: cycle

    started = time.perf_counter()
    try:
        library = parse_cql(measure_config.cql_path.read_text())
        output_columns = _all_column_names(library)
        # ``Measurement Period`` is a required parameter for every 2025 measure:
        # leaving it unset makes TRANSLATION fail, which would look like a bind
        # failure. Its value is an inlined literal, so the default is safe.
        bind_parameters = (
            dict(parameters)
            if parameters
            else {"Measurement Period": DEFAULT_MEASUREMENT_PERIOD}
        )
        sql, _gen_ms, _lib_ms = translate(
            conn,
            library,
            measure_config,
            output_columns,
            bind_parameters,
            None,  # patient_ids: row filtering only, no effect on binding
            audit_mode=False,
            library_cache=library_cache,
            strict_profiles=strict_profiles,
        )
    except Exception as exc:  # noqa: BLE001 - a measure that cannot TRANSLATE also fails
        return BindResult(
            measure_id=measure_config.id,
            ok=False,
            error_class=type(exc).__name__,
            error_message=f"[translate] {str(exc).strip()}",
            translate_ms=(time.perf_counter() - started) * 1000,
        )

    translate_ms = (time.perf_counter() - started) * 1000
    result = bind_check_sql(conn, sql, measure_config.id)
    return BindResult(
        measure_id=result.measure_id,
        ok=result.ok,
        error_class=result.error_class,
        error_message=result.error_message,
        sql_bytes=result.sql_bytes,
        sql_statements=result.sql_statements,
        translate_ms=translate_ms,
        bind_ms=result.bind_ms,
    )


def bind_check_suite(
    conn,
    configs: Sequence[MeasureConfig],
    *,
    all_columns: bool = True,
    strict_profiles: bool = True,
    parameters: dict | None = None,
    on_result: Callable[[BindResult], None] | None = None,
    library_cache: dict | None = None,
) -> BindSummary:
    """Bind-check every measure in ``configs`` (a whole suite, typically).

    Each measure is translated and planned independently; nothing is scored,
    no expected results are read, no row is scanned. ``on_result`` is called as
    each measure finishes so a caller can stream progress.
    """
    require_strict_connection(conn)
    ensure_bind_schema(conn)
    try:
        conn.execute(f"SET max_expression_depth TO {MAX_EXPRESSION_DEPTH}")
    except Exception:  # pragma: no cover - older DuckDB without the knob
        pass

    from .runner import _clear_runtime_state

    cache = {} if library_cache is None else library_cache
    summary = BindSummary()
    for config in configs:
        result = bind_check_measure(
            conn,
            config,
            all_columns=all_columns,
            strict_profiles=strict_profiles,
            library_cache=cache,
            parameters=parameters,
        )
        summary.results.append(result)
        if on_result is not None:
            on_result(result)
        # Per-measure cleanup, mirroring the scored loop in ``run_dqm.py``: a
        # 70-measure sweep otherwise accumulates every measure's ASTs and CTE
        # trees and grows to multi-GB RSS before it finishes.
        gc.collect()
        _clear_runtime_state(conn)
    return summary


__all__ = [
    "BindCheckError",
    "BindResult",
    "BindSummary",
    "DEFAULT_MEASUREMENT_PERIOD",
    "MAX_EXPRESSION_DEPTH",
    "STRICT_SETTING",
    "bind_check_measure",
    "bind_check_sql",
    "bind_check_suite",
    "bind_sql",
    "ensure_bind_schema",
    "require_strict_connection",
]
