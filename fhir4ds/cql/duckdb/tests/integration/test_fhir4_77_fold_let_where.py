"""FHIR4-77 — WHERE and LET clauses of an aggregate fold apply to the rows it folds.

A fold is a query: `from (…) X, (…) Y where … let N: … aggregate R starting …: …`. The WHERE
of a multi-source fold was added by FHIR4-73. A LET was never part of the fold: its expression
had been translated against the WHOLE source list, so a single-source body multiplied the list
itself (`TRY([1, 2, 3] * 2)`) and a multi-source body answered
`Referenced column "X" not found`. A single-source WHERE over a list literal did not bind
either: the filter was pushed into the select that produces the unnested column, which DuckDB
rejects, and the source was then correlated to the patient although it has no patient column.

Every case asserts CONTENT, never length or non-emptiness: a fold that answers NULL and a fold
that answers a truncated list are both failures.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_POPULATION = """library F77Fold version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Requests": [MedicationRequest]
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
define "D":
  __EXPR__
"""

_COLUMNS = {
    "Initial Population": "Initial Population",
    "Denominator": "Denominator",
    "Numerator": "Numerator",
    "D": "D",
}

_RESOURCES = [{"resourceType": "Patient", "id": "p1", "gender": "female"}]
_RESOURCES += [
    {
        "resourceType": "MedicationRequest",
        "id": mid,
        "status": status,
        "intent": "order",
        "subject": {"reference": "Patient/p1"},
    }
    for mid, status in (("m1", "active"), ("m2", "draft"))
]


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
    """Python supplements and the C++-only engine: the lowering must hold on both."""
    for build in (_python_connection, no_python_connection):
        with build() as con:
            yield con


def _sql(con, expression: str) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_POPULATION.replace("__EXPR__", expression))
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=_COLUMNS
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    for resource in _RESOURCES:
        patient_ref = (resource.get("subject") or {}).get("reference", "").split("/")[-1]
        if resource["resourceType"] == "Patient":
            patient_ref = resource["id"]
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [resource["id"], resource["resourceType"], json.dumps(resource), patient_ref],
        )


def _answer(con, expression: str):
    sql = _sql(con, expression)
    _load(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return [row[names.index("D")] for row in cursor.fetchall()], sql


def _sorted(value):
    return sorted(value) if isinstance(value, list) else value


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        # ── multi-source ────────────────────────────────────────────────────────────
        # (1+2+3)*2 doubled, for each of the two Y: 12 + 12.
        ("from ({1, 2, 3}) X, ({10, 20}) Y let N: X * 2 aggregate R starting 0: R + N", 24),
        # The let reads the SECOND source: 20 or 40 per row, three rows each.
        ("from ({1, 2, 3}) X, ({10, 20}) Y let N: Y * 2 aggregate R starting 0: R + N", 180),
        # The WHERE filters the rows the fold sees: X in {2, 3}.
        (
            "from ({1, 2, 3}) X, ({10, 20}) Y where X > 1 let N: X * 2 "
            "aggregate R starting 0: R + N",
            20,
        ),
        # A WHERE can read a let: N > 2 keeps X in {2, 3}.
        (
            "from ({1, 2, 3}) X, ({10, 20}) Y let N: X * 2 where N > 2 "
            "aggregate R starting 0: R + N",
            20,
        ),
        # A let reads the lets before it: M = 2X + Y.
        (
            "from ({1, 2}) X, ({10, 20}) Y let N: X * 2, M: N + Y aggregate R starting 0: R + M",
            72,
        ),
        # distinct applies to the joined rows, lets included: (1,1) and (2,1).
        (
            "from ({1, 2, 2}) X, ({1}) Y let N: X * 10 aggregate distinct R starting 0: R + N",
            30,
        ),
        (
            "from ({1, 2, 2}) X, ({1}) Y let N: X * 10 aggregate all R starting 0: R + N",
            50,
        ),
        # The WHERE alone keeps its FHIR4-73 answer.
        ("from ({1, 2, 3}) P, ({10, 20}) Q where P > 1 aggregate R starting 0: R + 1", 4),
        # ── single-source ───────────────────────────────────────────────────────────
        ("({1, 2, 3}) X let N: X * 2 aggregate R starting 0: R + N", 12),
        ("({1, 2, 3}) X where X > 1 let N: X * 2 aggregate R starting 0: R + N", 10),
        ("({1, 2, 3}) X where X > 1 aggregate R starting 0: R + X", 5),
        # A WHERE that leaves no row: the fold is its starting value.
        ("({1, 2, 3}) X where X > 9 aggregate R starting 0: R + X", 0),
        ("({1, 2, 2}) X let N: X * 10 aggregate distinct R starting 0: R + N", 30),
        # No clause at all: unchanged.
        ("({1, 2, 3}) X aggregate R starting 0: R + X", 6),
    ],
)
def test_where_and_let_clauses_of_a_fold_apply_to_its_rows(expression, expected):
    for con in _engines():
        answer, _ = _answer(con, expression)
        assert answer == [expected], expression


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (
            "from ({'a', 'b'}) X, ({'x', 'y'}) Y let N: X & Y "
            "aggregate R starting ({} as List<String>): R union {N}",
            ["ax", "ay", "bx", "by"],
        ),
        (
            "({'a', 'b'}) X let N: X & '!' "
            "aggregate R starting ({} as List<String>): R union {N}",
            ["a!", "b!"],
        ),
        # A let over a list accumulator still reads the element, not the accumulator.
        (
            "({'a', 'b', 'c'}) X let N: X & X "
            "aggregate R starting (null as List<String>): R union {N}",
            ["aa", "bb", "cc"],
        ),
    ],
)
def test_a_let_in_a_fold_with_a_list_accumulator(expression, expected):
    for con in _engines():
        answer, _ = _answer(con, expression)
        assert [_sorted(value) for value in answer] == [expected], expression


def test_a_let_over_retrieve_rows_counts_every_row():
    """Rows sources (retrieves) fold per resource; the let reads each resource's property."""
    for con in _engines():
        answer, _ = _answer(
            con, '("Requests" M let D: M.status aggregate R starting 0: R + 1)'
        )
        assert answer == [2]


def test_the_let_travels_in_the_working_table_and_the_where_stays_out_of_the_unnest():
    for con in _engines():
        sql = _sql(
            con,
            "from ({1, 2, 3}) X, ({10, 20}) Y let N: X * 2 "
            "aggregate R starting 0: R + N",
        )
        assert "__fold(__acc, __rn, __items, __c0, __c1, __c2) AS (" in sql, sql[:400]
        # One derived-table level per let, read as a column by the body.
        assert 'AS "N" FROM' in sql and '"N" := __d."N"' in sql, sql[:600]
        assert "list_reduce" not in sql
        # The single-source WHERE over a list literal filters the select that READS the
        # unnested column (never the select that produces it, which DuckDB rejects).
        sql = _sql(con, "({1, 2, 3}) X where X > 1 aggregate R starting 0: R + X")
        assert ") AS _list WHERE X > 1" in sql, sql[:900]
        # … and is never correlated to the patient (a list literal has no patient column).
        assert "X.patient_id = _pt.patient_id" not in sql


def test_rows_do_not_leak_across_patients():
    """Two patients with different numbers of requests: each folds its own rows."""
    expression = '("Requests" M let D: M.status aggregate R starting 0: R + 1)'
    for con in _engines():
        _sql(con, expression)
        con.execute(
            "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
            "resource JSON, patient_ref VARCHAR)"
        )
        for pid, count in (("p1", 2), ("p2", 1), ("p3", 0)):
            con.execute(
                "INSERT INTO resources VALUES (?, 'Patient', ?::JSON, ?)",
                [pid, json.dumps({"resourceType": "Patient", "id": pid}), pid],
            )
            for k in range(count):
                rid = f"{pid}-m{k}"
                con.execute(
                    "INSERT INTO resources VALUES (?, 'MedicationRequest', ?::JSON, ?)",
                    [
                        rid,
                        json.dumps(
                            {
                                "resourceType": "MedicationRequest",
                                "id": rid,
                                "status": "active",
                                "intent": "order",
                                "subject": {"reference": f"Patient/{pid}"},
                            }
                        ),
                        pid,
                    ],
                )
        cursor = con.execute(_sql(con, expression))
        names = [column[0] for column in cursor.description]
        assert {row[0]: row[names.index("D")] for row in cursor.fetchall()} == {
            "p1": 2,
            "p2": 1,
            "p3": 0,
        }
