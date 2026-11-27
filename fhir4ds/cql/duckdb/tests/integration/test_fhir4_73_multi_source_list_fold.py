"""FHIR4-73 — a multi-source aggregate with a list starting value.

``from (…) P, (…) Q aggregate R starting ({} as List<String>): R union { P & Q }`` is the fold idiom
the single-source form already supported. The multi-source fold cast EVERY starting value to
BIGINT, so a list-typed anchor did not bind (the body's ``list_concat`` met an integer accumulator)
and the define failed for every patient. A list starting value now gets the list-typed anchor the
single-source fold uses; every other starting value keeps the integer anchor.

Two neighbours of that defect failed the same queries and are fixed here too, because they make a
multi-source fold answer wrongly rather than fail:

* the query's WHERE clause was dropped, so the fold ran over rows the query had excluded;
* a membership test over the result (``"Pairs" contains 'ay'``) coerced the define's single row to
  a list again and tested a one-element list of the whole list.

The tests assert CONTENT (which elements), never a length or non-emptiness: NULL and a truncated
list are both failures of a fold.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_HEAD = """library FHIR473 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
"""

_FOLD = """define "Value":
  from ({sources_p}) P, ({sources_q}) Q __WHERE__ aggregate __KEYWORD__ R starting __START__: __BODY__
"""

_CONSUMERS = """define "Value Count": Count("Value")
define "Has Ay": "Value" contains 'ay'
define "Ay In Value": 'ay' in "Value"
define "First Value": First("Value")
"""

_COLUMNS = {
    "Initial Population": "Initial Population",
    "Denominator": "Denominator",
    "Numerator": "Numerator",
    "Value": "Value",
    "Value Count": "Value Count",
    "Has Ay": "Has Ay",
    "Ay In Value": "Ay In Value",
    "First Value": "First Value",
}

_ALL_PAIRS = ["ax", "ay", "bx", "by"]

_FOLD_SQL = re.compile(r"\(WITH RECURSIVE .*? SELECT __acc FROM __fold ORDER BY __rn DESC LIMIT 1\)", re.S)


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


def _library(
    *,
    start: str = "({} as List<String>)",
    body: str = "R union { P & Q }",
    keyword: str = "",
    where: str = "",
    sources_p: str = "'a', 'b'",
    sources_q: str = "'x', 'y'",
    consumers: bool = True,
) -> str:
    fold = (
        _FOLD.replace("{sources_p}", "{ " + sources_p + " }")
        .replace("{sources_q}", "{ " + sources_q + " }")
        .replace("__WHERE__", where)
        .replace("__KEYWORD__", keyword)
        .replace("__START__", start)
        .replace("__BODY__", body)
    )
    return _HEAD + fold + (_CONSUMERS if consumers else "")


def _translate(con, library: str, columns: dict) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    parsed = parse_cql(library)
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(parsed)
    return translator.translate_library_to_population_sql(library=parsed, output_columns=columns)


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    for pid in ("p1", "p2"):
        con.execute(
            "INSERT INTO resources VALUES (?,'Patient',?::JSON,?)",
            [pid, json.dumps({"resourceType": "Patient", "id": pid}), pid],
        )


def _rows(con, sql: str) -> dict:
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return {str(row[0]): dict(zip(names, row, strict=True)) for row in cursor.fetchall()}


def _value_column(con, library: str, definition: str) -> list:
    """The folded value for every patient, on this engine."""
    sql = _translate(con, library, {"Initial Population": "Initial Population", definition: definition})
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return [row[names.index(definition)] for row in cursor.fetchall()]


def _assert_folded_pairs(row: dict) -> None:
    assert sorted(row["Value"]) == _ALL_PAIRS, row["Value"]
    assert row["Value Count"] == 4, row
    assert row["Has Ay"] is True and row["Ay In Value"] is True, row
    assert row["First Value"] in _ALL_PAIRS, row


_ANCHORS = (
    ("({} as List<String>)", "SELECT CAST([] AS VARCHAR[]) AS __acc, CAST(0 AS BIGINT) AS __rn"),
    ("(null as List<String>)", "SELECT CAST(NULL AS VARCHAR[]) AS __acc, CAST(0 AS BIGINT) AS __rn"),
)


@pytest.mark.parametrize(("start", "anchor"), _ANCHORS)
def test_the_anchor_of_a_list_accumulator_is_a_list_not_an_integer(start, anchor):
    """The lowering invariant: every fold carries a list-typed anchor, never an integer one."""
    for con in _engines():
        sql = _translate(con, _library(start=start), _COLUMNS)
        folds = _FOLD_SQL.findall(sql)
        assert folds and len(folds) == sql.count("WITH RECURSIVE"), len(folds)
        for fold in folds:
            assert anchor in fold, fold[:400]


def test_an_empty_list_starting_value_folds_every_pair():
    for con in _engines():
        _load(con)
        rows = _rows(con, _translate(con, _library(), _COLUMNS))
        assert set(rows) == {"p1", "p2"}, set(rows)
        for row in rows.values():
            _assert_folded_pairs(row)


def test_a_null_list_starting_value_folds_every_pair():
    """``null as List<T>`` starts from SQL NULL: the first step must treat it as an empty list."""
    for con in _engines():
        _load(con)
        rows = _rows(con, _translate(con, _library(start="(null as List<String>)"), _COLUMNS))
        for row in rows.values():
            _assert_folded_pairs(row)


def test_no_source_rows_leaves_the_starting_value():
    """CQL 1.5 §19.27: an aggregate over an empty list does not evaluate its body."""
    for con in _engines():
        _load(con)
        rows = _rows(con, _translate(con, _library(where="where P = 'zz'"), _COLUMNS))
        for row in rows.values():
            assert row["Value"] == [], row["Value"]
            assert row["Value Count"] == 0, row
            assert row["First Value"] is None, row


@pytest.mark.parametrize(
    ("start", "body", "keyword", "where", "sources_p", "sources_q", "expected"),
    [
        # Only the pairs with P > 1 are folded: four rows, one increment each.
        ("0", "R + 1", "", "where P > 1", "1, 2, 3", "10, 20", [4, 4]),
        # A scalar fold with no WHERE clause keeps every pair (regression guard).
        ("0", "R + 1", "", "", "1, 2, 3", "10, 20", [6, 6]),
        # The WHERE clause may reference either source alias.
        ("({} as List<String>)", "R union { P & Q }", "", "where Q = 'y'", "'a', 'b'", "'x', 'y'",
         [["ay", "by"], ["ay", "by"]]),
        ("({} as List<String>)", "R union { P & Q }", "", "where Q = 'y' and P = 'a'",
         "'a', 'b'", "'x', 'y'", [["ay"], ["ay"]]),
        # ``distinct`` applies to the cross-joined pairs the WHERE clause keeps.
        ("({} as List<String>)", "R union { P & Q }", "distinct", "", "'a', 'a'", "'x'",
         [["ax"], ["ax"]]),
        ("({} as List<String>)", "R union { P & Q }", "distinct", "where Q = 'y'",
         "'a', 'a', 'b'", "'x', 'y'", [["ay", "by"], ["ay", "by"]]),
    ],
)
def test_the_where_clause_filters_the_rows_the_fold_sees(
    start, body, keyword, where, sources_p, sources_q, expected
):
    """Before the fix the WHERE clause was dropped, so every pair was folded."""
    library = _library(
        start=start, body=body, keyword=keyword, where=where,
        sources_p=sources_p, sources_q=sources_q, consumers=False,
    )
    for con in _engines():
        _load(con)
        values = _value_column(con, library, "Value")
        # A fold's element order is the join order DuckDB happens to pick: compare lists as sets.
        for value, want in zip(values, expected, strict=True):
            if isinstance(want, list):
                assert sorted(value) == sorted(want), values
            else:
                assert value == want, values


def test_a_scalar_starting_value_keeps_its_integer_anchor():
    """The scalar case keeps its content, with an anchor of the starting value's type.

    FHIR4-76 replaced the BIGINT cast every scalar start used to get by the starting value's own
    type, so an Integer start anchors as INTEGER (and Integer overflow is null, per CQL).
    """
    library = _library(
        start="0", body="R + P + Q", consumers=False,
        sources_p="1, 2, 3", sources_q="10, 20",
    )
    for con in _engines():
        _load(con)
        sql = _translate(con, library, {"Initial Population": "Initial Population", "Value": "Value"})
        folds = _FOLD_SQL.findall(sql)
        assert folds and all(
            "SELECT CAST(0 AS INTEGER) AS __acc, CAST(0 AS BIGINT) AS __rn" in fold for fold in folds
        ), folds[0][:300]
        values = _value_column(con, library, "Value")
    assert values == [102, 102], values


def test_the_list_fold_does_not_depend_on_the_plan():
    """The multi-source list fold has the WP-11 shape, so every execution answers the same."""
    for con in _engines():
        _load(con)
        sql = _translate(con, _library(), _COLUMNS)
        recursive_term = sql[sql.index("UNION ALL") : sql.index("SELECT __acc FROM __fold")]
        assert "JOIN" not in recursive_term and "ROW_NUMBER" not in sql, recursive_term
        # NEVER pin threads=1: a plan-dependent defect only exists in parallel execution.
        con.execute("SET threads=4")
        for i in range(100):
            rows = _rows(con, sql)
            for row in rows.values():
                assert sorted(row["Value"]) == _ALL_PAIRS, (
                    f"execution {i} answered {row['Value']}; expected {_ALL_PAIRS}"
                )
        con.execute("RESET threads")
