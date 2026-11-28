"""FHIR4-114 — an aggregate over a stored list DEFINE keeps the CQL result type.

CQL 1.5 Appendix B gives every aggregate a typed result: ``Sum(List<Integer>) Integer``,
``Sum(List<Long>) Long``, ``Avg(List<T>) Decimal``. The literal spelling honoured that; the
same aggregate over a stored-list define alias did NOT:

    define "L": {1, 2, 3}
    define "SumLiteral": Sum({1, 2, 3})     -- 6,   DuckDB column type INTEGER   (right)
    define "SumAlias":   Sum("L")           -- 6.0, DuckDB column type DOUBLE     (wrong)

The VALUE looked right, which is why this survived: it is the TYPE that is wrong. Downstream
every type-sensitive consumer then sees a DOUBLE — ``Sum("L") is Integer`` answers false,
``ToInteger`` and an exact-equality assertion take the floating path — and CQL's Integer
overflow-to-null rule stops applying at all: ``Sum({2147483647, 1})`` answers null where
``Sum("L")`` over the same elements answered ``2147483648.0``, a value that is not a valid
CQL Integer.

The cause is in the translator, not the engine: the stored-list define branch of
``_translate_aggregate_pre`` mapped ``sum``/``avg`` straight onto DuckDB's ``list_sum`` /
``list_avg``, whose normalization casts every element to DOUBLE, and returned BEFORE the
typed dispatcher (``_translate_list_aggregate_dispatch``) ever saw the element types — even
though the define's ``cql_type`` already said ``List<Integer>``. The dispatcher is what
restores the CQL result width, exactly as it already did for the literal spelling.

The declared element type is not always the column's physical type, and the same branch has
to survive that: a `List<Integer>` define built from duration expressions transports VARCHAR
text (`months between …` answers '1', not 1), so the aggregate casts each element to the CQL
element type at the list boundary before the exact aggregate runs. Without that cast the
typed lowering would be a Binder Error (`sum(VARCHAR)`), which is what the first version of
this fix did to `Sum({ months between …, months between … })`.

These tests assert the DuckDB COLUMN TYPE and the value, on both engines (the defect is
translator-level, so the lowering must be right for the Python and the C++ surfaces alike).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

LIBRARY = """library FHIR4_114 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists (Patient)

// Element types: Integer, Long, Decimal, plus the two boundary shapes.
define "L": {1, 2, 3}
define "LLong": {1L, 2L, 3L}
define "LDecimal": {1.5, 2.5}
define "LOverflow": {2147483647, 1}
define "LEmpty": {} as List<Integer>
// A CTE-backed list (not an inlined literal): the source is the define's value column.
define "LDistinct": distinct "L"
// Declared List<Integer>, physically VARCHAR: duration answers TEXT ('1', not 1).
define "LDuration": { months between @2020-01-01 and @2020-02-01, months between @2020-01-01 and @2020-03-01 }
define "LUncertain": { days between @2020-01 and @2020-02-01 }

// The defect: aggregate over the DEFINE ALIAS.
define "SumAlias": Sum("L")
define "SumLongAlias": Sum("LLong")
define "SumDecimalAlias": Sum("LDecimal")
define "SumOverflowAlias": Sum("LOverflow")
define "SumEmptyAlias": Sum("LEmpty")
define "SumCteBackedAlias": Sum("LDistinct")
define "AvgAlias": Avg("L")
define "SumDurationAlias": Sum("LDuration")
define "AvgDurationAlias": Avg("LDuration")
define "MinDurationAlias": Min("LDuration")
// An element the declared type cannot represent (an uncertainty interval) is dropped, not an error.
define "SumUncertainAlias": Sum("LUncertain")

// The reference spellings (already correct — pinned so a regression cannot hide behind them).
define "SumLiteral": Sum({1, 2, 3})
define "SumLongLiteral": Sum({1L, 2L, 3L})
define "SumOverflowLiteral": Sum({2147483647, 1})

// Downstream consumers of the type, which is what makes the type a correctness question.
define "SumIsInteger": Sum("L") is Integer
define "SumIsNull": Sum("LOverflow") is null

// Unchanged neighbours: Min/Max/Count/Product/Median never took the DOUBLE list cast.
define "MinAlias": Min("L")
define "MaxAlias": Max("L")
define "CountAlias": Count("L")
define "ProductAlias": Product("L")
define "MedianAlias": Median("L")
"""

COLUMNS = {
    "SumAlias": "SumAlias",
    "SumLongAlias": "SumLongAlias",
    "SumDecimalAlias": "SumDecimalAlias",
    "SumOverflowAlias": "SumOverflowAlias",
    "SumEmptyAlias": "SumEmptyAlias",
    "SumCteBackedAlias": "SumCteBackedAlias",
    "AvgAlias": "AvgAlias",
    "SumDurationAlias": "SumDurationAlias",
    "AvgDurationAlias": "AvgDurationAlias",
    "MinDurationAlias": "MinDurationAlias",
    "SumUncertainAlias": "SumUncertainAlias",
    "SumLiteral": "SumLiteral",
    "SumLongLiteral": "SumLongLiteral",
    "SumOverflowLiteral": "SumOverflowLiteral",
    "SumIsInteger": "SumIsInteger",
    "SumIsNull": "SumIsNull",
    "MinAlias": "MinAlias",
    "MaxAlias": "MaxAlias",
    "CountAlias": "CountAlias",
    "ProductAlias": "ProductAlias",
    "MedianAlias": "MedianAlias",
}

#: column -> (DuckDB column type, value for the single patient).
EXPECTED: dict[str, tuple[str, object]] = {
    # ── The card: Sum(List<Integer>) is an Integer, whatever spelling carries the list ──────
    "SumAlias": ("INTEGER", 6),
    "SumLiteral": ("INTEGER", 6),
    "SumCteBackedAlias": ("INTEGER", 6),
    # ── Sum(List<Long>) is a Long; Sum(List<Decimal>) stays Decimal (exact, never DOUBLE) ──
    "SumLongAlias": ("BIGINT", 6),
    "SumLongLiteral": ("BIGINT", 6),
    "SumDecimalAlias": ("DECIMAL", Decimal("4.0")),
    # ── CQL Integer overflow is null, not a laundered out-of-range Double ──────────────────
    "SumOverflowAlias": ("INTEGER", None),
    "SumOverflowLiteral": ("INTEGER", None),
    "SumEmptyAlias": ("INTEGER", None),
    # ── Avg(List<T>) is Decimal per Appendix B ─────────────────────────────────────────────
    "AvgAlias": ("DECIMAL", Decimal("2.0")),
    # ── A declared List<Integer> that transports TEXT (duration) still aggregates exactly ──
    "SumDurationAlias": ("INTEGER", 3),
    "AvgDurationAlias": ("DECIMAL", Decimal("1.5")),
    "MinDurationAlias": ("INTEGER", 1),
    "SumUncertainAlias": ("INTEGER", None),
    # ── Downstream type-sensitive consumers ────────────────────────────────────────────────
    "SumIsInteger": ("BOOLEAN", True),
    "SumIsNull": ("BOOLEAN", True),
    # ── Unchanged neighbours ───────────────────────────────────────────────────────────────
    "MinAlias": ("INTEGER", 1),
    "MaxAlias": ("INTEGER", 3),
    "CountAlias": ("BIGINT", 3),
    "ProductAlias": ("INTEGER", 6),
    "MedianAlias": ("DECIMAL", Decimal("2.0")),
}
assert set(EXPECTED) == set(COLUMNS), "every projected define has an expected answer"


@contextmanager
def _python_connection():
    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    try:
        yield con
    finally:
        con.close()


def _engines() -> Iterator[tuple[str, duckdb.DuckDBPyConnection]]:
    """The Python-supplement engine and the C++-only engine: the lowering must hold on both."""
    for label, build in (("python", _python_connection), ("c++", no_python_connection)):
        with build() as con:
            con.execute(
                "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
                "resource JSON, patient_ref VARCHAR)"
            )
            con.execute(
                "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                [
                    "p1",
                    "Patient",
                    json.dumps({"resourceType": "Patient", "id": "p1"}),
                    "p1",
                ],
            )
            yield label, con


def _population(con) -> tuple[dict[str, tuple[str, object]], str]:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(LIBRARY)
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *args: None)
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(
        library=library, output_columns=COLUMNS
    )
    description = con.execute(f"DESCRIBE ({sql})").fetchall()
    types = {row[0]: row[1] for row in description}
    names = [row[0] for row in description]
    rows = con.execute(sql).fetchall()
    assert len(rows) == 1, f"expected one patient row, got {len(rows)}"
    answers = {name: (types[name], rows[0][names.index(name)]) for name in names if name in COLUMNS}
    return answers, sql


def _matches(expected_type: str, actual_type: str) -> bool:
    """``DECIMAL`` in the table means "a DECIMAL family type", not one exact width."""
    if expected_type == "DECIMAL":
        return actual_type.startswith("DECIMAL")
    return actual_type == expected_type


@pytest.mark.parametrize("column", sorted(EXPECTED))
def test_an_aggregate_over_a_stored_list_define_keeps_its_cql_type(column: str) -> None:
    expected_type, expected_value = EXPECTED[column]
    for label, con in _engines():
        answers, _ = _population(con)
        actual_type, actual_value = answers[column]
        assert _matches(expected_type, actual_type), (
            f"[{label}] {column}: column type {actual_type!r} is not {expected_type}"
        )
        assert actual_value == expected_value, (
            f"[{label}] {column}: {actual_value!r} != {expected_value!r}"
        )


def test_a_numeric_stored_list_is_not_lowered_through_the_double_list_aggregates() -> None:
    """``list_sum``/``list_avg`` cast every element to DOUBLE; the typed dispatcher does not.

    This is the mechanism pin: the type defect and the ``list_sum`` lowering are one thing.
    """
    for label, con in _engines():
        _, sql = _population(con)
        # Every Sum/Avg in this library is numeric, so none of them may take the
        # DOUBLE-element list aggregate.
        assert "list_sum(" not in sql, f"[{label}] list_sum casts elements to DOUBLE"
        assert "list_avg(" not in sql, f"[{label}] list_avg casts elements to DOUBLE"
        assert "TRY_CAST(list_aggregate(" in sql, (
            f"[{label}] the CQL result width is not restored with TRY_CAST"
        )
