"""FHIR4-84 — a fold WITHOUT a starting value uses the same working table, typed from its BODY.

CQL 1.5 §Aggregate Queries: "if no starting clause is specified, the aggregation result is
initially null", which is why the spec's own no-start example is
``aggregate Result: Coalesce(Result, 1) * Num`` — the accumulator starts NULL and the body must
normalise it. So a no-start fold's accumulator type has to come from the BODY (the body's result
is what the next step reads), and it has to live in the fold's working table like every other
accumulator (FHIR4-76).

It did neither: a no-start fold was the only one still lowered through ``list_reduce``, whose
accumulator lives INSIDE the element list and is therefore cast to the ELEMENT type on every
step, and whose ``let`` was translated against the WHOLE source list:

* ``({1, 2, 3}) N aggregate A: Coalesce(A, 0.0) + 0.5`` answered **0** where the same fold with
  ``starting 0.0`` answers 1.5 (every step was cast back to the Integer element type);
* ``({1, 2, 3}) N let M: N * 2 aggregate A: Coalesce(A, 0) + M`` was a Binder Error
  (``*(INTEGER[], INTEGER)``);
* a Quantity accumulator answered NULL, and a list accumulator (``A union {N}``) failed to bind
  (``list_concat(VARCHAR, VARCHAR[])``).

Every case asserts a VALUE and, where a control exists, the same fold with an explicit starting
value — because a test that only pinned the value could pass while the fold answered the right
number for the wrong reason.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from decimal import Decimal

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_LIBRARY = """library FHIR4_84 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Nums": {1, 2, 3}
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
define "NoStart":
  __NO_START__
define "WithStart":
  __WITH_START__
"""

#: Column label -> CQL definition name. The population SQL projects both folds, so the two
#: answers come from ONE execution over the same data.
_COLUMNS = {
    "Initial Population": "Initial Population",
    "Denominator": "Denominator",
    "Numerator": "Numerator",
    "NoStart": "NoStart",
    "WithStart": "WithStart",
}

_SQL_INTEGER = "INTEGER"
_SQL_DECIMAL = "DECIMAL(38,8)"


@contextmanager
def _python_connection():
    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    try:
        yield con
    finally:
        con.close()


def _engines():
    """Python supplements and the C++-only engine: the lowering is translator-side, both agree."""
    for build in (_python_connection, no_python_connection):
        with build() as con:
            yield con


def _library(no_start: str, with_start: str) -> str:
    return _LIBRARY.replace("__NO_START__", no_start).replace("__WITH_START__", with_start)


def _sql(con, no_start: str, with_start: str) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_library(no_start, with_start))
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=_COLUMNS
    )


def _load_patient(con, resources=None) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    for resource in resources or [{"resourceType": "Patient", "id": "p1"}]:
        con.execute(
            "INSERT INTO resources VALUES (?, ?, ?::JSON, ?)",
            [
                resource["id"],
                resource["resourceType"],
                json.dumps(resource),
                resource.get("patient_ref", resource["id"]),
            ],
        )


def _answers(con, no_start: str, with_start: str, resources=None):
    """(no-start value, no-start SQL type, with-start value) for p1, from ONE execution."""
    sql = _sql(con, no_start, with_start)
    _load_patient(con, resources)
    cursor = con.execute(
        f'SELECT ("NoStart"), typeof(("NoStart")), ("WithStart") FROM ({sql}) AS _pop'
    )
    rows = cursor.fetchall()
    assert len(rows) == 1, rows
    return rows[0]


#: (id, source + alias, body, explicit starting value of the BODY's type, expected value, SQL type).
#: The no-start fold and the control are the same fold written twice.
_CASES = [
    # ── the accumulator is typed from the BODY, not from the element ────────────────────────
    ("DecimalBody", "({1, 2, 3}) N", "Coalesce(A, 0.0) + 0.5", "0.0", Decimal("1.5"), _SQL_DECIMAL),
    # 0 + 0.125 + 0.125 + 0.125: no step is rounded to the Integer element type.
    (
        "DecimalStepNoElementRounding",
        "({1, 1, 1}) N",
        "Coalesce(A, 0.0) + 0.125",
        "0.0",
        Decimal("0.375"),
        _SQL_DECIMAL,
    ),
    ("IntegerBody", "({1, 2, 3}) N", "Coalesce(A, 0) + N", "0", 6, _SQL_INTEGER),
    ("LongBody", "({1L, 2L}) N", "Coalesce(A, 0L) + 1L", "0L", 2, "BIGINT"),
    ("StringBody", "({'a', 'b', 'c'}) N", "Coalesce(A, '') & N", "''", "abc", "VARCHAR"),
    ("BooleanBody", "({1, 2, 3}) N", "Coalesce(A, false) or N > 1", "false", True, "BOOLEAN"),
    ("DateBody", "({1, 2}) N", "Coalesce(A, @2023-12-31) + 1 day", "@2023-12-31", "2024-01-02", "VARCHAR"),
    # A list accumulator: the anchor is a CAST(NULL AS VARCHAR[]) instead of a VARCHAR null,
    # which is what makes `R union {N}` bind at all.
    ("ListBody", "({'a', 'b'}) N", "A union {N}", "(null as List<String>)", ["a", "b"], "VARCHAR[]"),
    # ── the source is a define, the alias is the definition's elements ──────────────────────
    ("DefineSource", '"Nums" N', "Coalesce(A, 0) + N", "0", 6, _SQL_INTEGER),
    # ── multi-source: the anchor used to be a fixed BIGINT, which truncated a Decimal body ──
    (
        "MultiSourceDecimalBody",
        "from ({1, 2}) N, ({10}) M",
        "Coalesce(A, 0.0) + 0.5",
        "0.0",
        Decimal("1.0"),
        _SQL_DECIMAL,
    ),
    (
        "MultiSourceIntegerBody",
        "from ({1, 2}) N, ({10}) M",
        "Coalesce(A, 0) + N",
        "0",
        3,
        _SQL_INTEGER,
    ),
]


def _same(got, expected) -> bool:
    if isinstance(expected, Decimal):
        return isinstance(got, Decimal) and got == expected
    if isinstance(expected, bool):
        return isinstance(got, bool) and got is expected
    if isinstance(expected, list):
        return got is not None and sorted(got) == sorted(expected)
    return got == expected


@pytest.mark.parametrize(
    ("_id", "source", "body", "control_start", "expected", "sql_type"),
    _CASES,
    ids=[case[0] for case in _CASES],
)
def test_a_no_start_fold_answers_what_the_same_fold_with_a_start_answers(
    _id, source, body, control_start, expected, sql_type
):
    """The value AND the with-start control, so the fold cannot answer right by luck."""
    no_start = f"{source} aggregate A: {body}"
    with_start = f"{source} aggregate A starting {control_start}: {body}"
    for con in _engines():
        value, got_type, control = _answers(con, no_start, with_start)
        assert _same(value, expected), f"{no_start} answered {value!r} ({got_type})"
        assert got_type == sql_type, f"{no_start} typed {got_type}"
        assert _same(control, expected), f"control {with_start} answered {control!r}"
        assert _same(value, control), f"{no_start} = {value!r} but control = {control!r}"


def test_a_no_start_fold_starts_from_null_and_a_coalesce_body_normalises_it():
    """CQL 1.5 §Aggregate Queries: with no starting value the accumulator is initially null.

    The spec's own no-start example is ``aggregate Result: Coalesce(Result, 1) * Num`` — the
    body has to handle the null. A body that does NOT handle it therefore answers null, and the
    fold with an explicit NULL starting value of the body's type answers the same null. (This
    is why ``CoalesceMoreThan…``-style bodies are the only meaningful no-start folds: the
    fixture ``AggregateEmptySourceNoStart`` in the official corpus pins the same rule.)
    """
    for name, source, body, typed_null in (
        ("Decimal", "({1, 2, 3}) N", "A + 0.5", "(null as Decimal)"),
        ("Integer", "({1, 2, 3}) N", "A + 1", "(null as Integer)"),
        # `&` is NOT in this list: CQL's `&` ignores nulls (`null & 'x'` is 'x'), so a fold over
        # two elements answers 'xx' — spec-correct, and the typed-null control answers it too.
        ("Date", "({1, 2}) N", "A + 1 day", "(null as Date)"),
    ):
        no_start = f"{source} aggregate A: {body}"
        with_start = f"{source} aggregate A starting {typed_null}: {body}"
        for con in _engines():
            value, _, control = _answers(con, no_start, with_start)
            assert value is None, f"{name}: {no_start} answered {value!r}, expected null"
            assert control is None, f"{name}: control answered {control!r}"


def test_an_empty_source_with_no_start_stays_at_the_initial_null():
    """The official fixture ``AggregateEmptySourceNoStart``: no iterations, so the ACCUMULATOR
    keeps its initial value — which is null, not the body's zero."""
    for con in _engines():
        value, _, control = _answers(
            con,
            "({} as List<Integer>) N aggregate A: Coalesce(A, 0) + N",
            "({} as List<Integer>) N aggregate A starting (null as Integer): Coalesce(A, 0) + N",
        )
        assert value is None, value
        assert control is None, control
        # …and the same fold WITH a starting value keeps it, so the two paths are distinct.
        zero, _, _ = _answers(
            con,
            "({} as List<Integer>) N aggregate A starting 0: Coalesce(A, 0) + N",
            "({} as List<Integer>) N aggregate A: Coalesce(A, 0) + N",
        )
        assert zero == 0, zero


def test_a_no_start_fold_evaluates_its_let_against_the_source_rows():
    """A ``let`` belongs to the fold's rows (FHIR4-77); without a starting value it used to be
    translated against the WHOLE source list, which is a Binder Error."""
    no_start = "({1, 2, 3}) N let M: N * 2 aggregate A: Coalesce(A, 0) + M"
    with_start = "({1, 2, 3}) N let M: N * 2 aggregate A starting 0: Coalesce(A, 0) + M"
    for con in _engines():
        value, _, control = _answers(con, no_start, with_start)
        assert value == 12, value
        assert value == control, (value, control)
        sql = _sql(con, no_start, with_start)
        # The let travels in the working table as its own column, exactly as with a start.
        assert '"M" := __d."M"' in sql, sql[:800]
        assert 'AS "M" FROM' in sql, sql[:800]


def test_a_quantity_accumulator_without_a_start_still_accumulates_quantities():
    no_start = "({1 'mg', 2 'mg'}) N aggregate A: Coalesce(A, 0 'mg') + N"
    with_start = "({1 'mg', 2 'mg'}) N aggregate A starting 0 'mg': Coalesce(A, 0 'mg') + N"
    for con in _engines():
        value, _, control = _answers(con, no_start, with_start)
        assert value is not None, "a no-start Quantity fold answered NULL"
        quantity = json.loads(value)
        assert (quantity["value"], quantity["unit"]) == (3.0, "mg"), quantity
        assert json.loads(control) == quantity, (value, control)


def test_distinct_and_all_keep_their_meaning_without_a_start():
    cases = [
        ("({1, 1, 2, 3}) N aggregate distinct A: Coalesce(A, 0) + N", 6),
        ("({1, 1, 2, 3}) N aggregate all A: Coalesce(A, 0) + N", 7),
    ]
    for expression, expected in cases:
        control = expression.replace("aggregate distinct A:", "aggregate distinct A starting 0:").replace(
            "aggregate all A:", "aggregate all A starting 0:"
        )
        for con in _engines():
            value, _, control_value = _answers(con, expression, control)
            assert value == expected, (expression, value)
            assert value == control_value, (expression, value, control_value)


_FOLD = re.compile(
    r"\(WITH RECURSIVE __fold\(__acc, __rn, __items, [^)]*\) AS \(.*?"
    r"SELECT __acc FROM __fold ORDER BY __rn DESC LIMIT 1\)",
    re.S,
)


def test_a_no_start_fold_lowers_through_the_same_working_table():
    """No third lowering: the recursive working table, with a typed NULL anchor."""
    for con in _engines():
        sql = _sql(
            con,
            "({1, 2, 3}) N aggregate A: Coalesce(A, 0.0) + 0.5",
            "({1, 2, 3}) N aggregate A starting 0.0: Coalesce(A, 0.0) + 0.5",
        )
        folds = _FOLD.findall(sql)
        assert len(folds) == 2, sql
        assert "CAST(NULL AS DECIMAL(38,8)) AS __acc" in folds[0], folds[0][:400]
        # …and the accumulator never lives inside the element list.
        assert "list_reduce" not in sql, sql[:400]


def test_a_no_start_fold_does_not_depend_on_the_query_plan():
    """The working table is what makes the recursion plan-independent (WP-11). Same SQL, many
    executions, every thread count: one answer."""
    expression = "({'a', 'b', 'c'}) N aggregate A: Coalesce(A, '') & N"
    for con in _engines():
        sql = _sql(con, expression, expression)
        _load_patient(con)
        for threads in (4, 8):
            con.execute(f"PRAGMA threads={threads}")
            for _ in range(50):
                cursor = con.execute(
                    f'SELECT ("NoStart") FROM ({sql}) AS _pop'
                )
                assert cursor.fetchall() == [("abc",)], expression
        con.execute("PRAGMA threads=1")
