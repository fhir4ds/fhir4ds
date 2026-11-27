"""WP-11 — the recursive fold must not depend on the query plan.

A define whose value is an aggregate over a listified tuple query lowers to a recursive CTE.
In its first shape the recursive step JOINED the working table to a second table built by an
``unnest`` of a correlated subquery and a ``ROW_NUMBER()`` window, and nothing guaranteed that
join's build side was complete when the recursion read it. On duckdb-python 1.5.6 the very same
SQL then answered NULL (the anchor-only row survives when the element list comes back empty) or
a truncated list in about half of the executions at ``threads=4`` and in 3-9% at the default
thread count, while it was always right at ``threads=1``. It varied per EXECUTION inside one
connection, so one connection executed many times is both a faithful and a cheap detector.

The fold now carries the element list and the current element inside the working table: the
recursive term reads only that table (a filter and a projection), so no other pipeline has to
finish first.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_LIBRARY = """library WP11Fold version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Requests": [MedicationRequest]
define "Ids":
  ("Requests" M return all {id: M.id, authored: M.authoredOn} sort by authored).id I
    aggregate R starting (null as List<String>): R union {I}
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
"""

_COLUMNS = {
    "Initial Population": "Initial Population",
    "Denominator": "Denominator",
    "Numerator": "Numerator",
    "Ids": "Ids",
}

#: p1 has three requests that share authoredOn (the sort must still order them, by id);
#: p2 has none (an aggregate over an empty list is its starting value: null); p3 has one.
_RESOURCES = [{"resourceType": "Patient", "id": "p1", "gender": "female"}]
_RESOURCES += [
    {
        "resourceType": "MedicationRequest",
        "id": mid,
        "status": "active",
        "intent": "order",
        "subject": {"reference": "Patient/p1"},
        "authoredOn": "2026-03-01",
    }
    for mid in ("m-c", "m-b", "m-a")
]
_RESOURCES += [
    {"resourceType": "Patient", "id": "p2", "gender": "male"},
    {"resourceType": "Patient", "id": "p3", "gender": "female"},
    {
        "resourceType": "MedicationRequest",
        "id": "m-d",
        "status": "active",
        "intent": "order",
        "subject": {"reference": "Patient/p3"},
        "authoredOn": "2026-03-02",
    },
]

_EXPECTED = {"p1": ["m-a", "m-b", "m-c"], "p2": None, "p3": ["m-d"]}

#: Executions per engine and thread count. Before the fix a single execution at threads=4 was
#: wrong about half the time, so 200 executions miss a regression with probability 2**-200.
_RUNS = {4: 200, 8: 60}

_FOLD = re.compile(
    r"\(WITH RECURSIVE .*? SELECT __acc FROM __fold ORDER BY __rn DESC LIMIT 1\)", re.S
)


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


def _translate(con, library_text: str, columns: dict) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(library_text)
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=columns
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    for resource in _RESOURCES:
        patient_ref = (
            (resource.get("subject") or {}).get("reference", "").split("/")[-1] or None
        )
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [resource["id"], resource["resourceType"], json.dumps(resource), patient_ref],
        )


def _column(con, sql: str, column: str) -> dict:
    cursor = con.execute(sql)
    names = [column_[0] for column_ in cursor.description]
    return {str(row[0]): row[names.index(column)] for row in cursor.fetchall()}


def _ids(con, sql: str) -> dict:
    return {
        patient: None if ids is None else (sorted(ids) if isinstance(ids, list) else ids)
        for patient, ids in _column(con, sql, "Ids").items()
    }


def test_the_recursive_term_reads_only_the_working_table():
    """The lowering invariant the stability below depends on.

    The element list and the current element live in the working table; the recursive term is a
    filter and a projection over ``__fold`` — no join with a second table, no ``unnest`` and no
    window inside the recursion.
    """
    for con in _engines():
        sql = _translate(con, _LIBRARY, _COLUMNS)
    folds = _FOLD.findall(sql)
    assert len(folds) == 1, f"{len(folds)} recursive folds in the population SQL"
    fold = folds[0]
    assert "__fold(__acc, __rn, __items, __cur) AS (" in fold, fold[:400]
    recursive_term = fold[fold.index("UNION ALL") :]
    assert "JOIN" not in recursive_term, recursive_term
    assert "unnest" not in recursive_term.lower(), recursive_term
    assert "ROW_NUMBER" not in fold, fold
    assert "FROM __fold WHERE __fold.__rn < len(__fold.__items)" in recursive_term, recursive_term
    # Each step advances the counter once and projects the element of the NEXT step.
    assert "__fold.__rn + 1, __fold.__items, list_extract(__fold.__items, __fold.__rn + 2)" in (
        recursive_term
    ), recursive_term
    # The body reads the element of the CURRENT step from a plain column.
    assert "[__fold.__cur]" in recursive_term, recursive_term
    assert "__xjn" not in sql and "__xj AS" not in sql


def test_the_fold_answer_does_not_depend_on_the_plan():
    """Every execution answers the same, on both engines, at more than one thread count."""
    for con in _engines():
        sql = _translate(con, _LIBRARY, _COLUMNS)
        _load(con)
        for threads, runs in _RUNS.items():
            # NEVER pin threads=1: the defect only exists in parallel execution.
            con.execute(f"SET threads={threads}")
            wrong = None
            for i in range(runs):
                got = _ids(con, sql)
                if got != _EXPECTED:
                    wrong = (i, got)
                    break
            assert wrong is None, (
                f"threads={threads}: execution {wrong[0]} answered {wrong[1]}; "
                f"expected {_EXPECTED}"
            )
        con.execute("RESET threads")


_MULTI_SOURCE = """library WP11Multi version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
define "__DEFINITION__":
  from __SOURCES__ aggregate __KEYWORD__ __ACC__ starting __START__: __BODY__
"""


def _multi_source(
    define: str, sources: str, keyword: str, accumulator: str, start: str, body: str
) -> str:
    text = _MULTI_SOURCE.replace("__DEFINITION__", define).replace("__SOURCES__", sources)
    for marker, value in (
        ("__KEYWORD__", keyword), ("__ACC__", accumulator), ("__START__", start), ("__BODY__", body)
    ):
        text = text.replace(marker, value)
    return text


@pytest.mark.parametrize(
    ("define", "sources", "keyword", "accumulator", "start", "body", "expected"),
    [
        # Every cross-joined pair is folded once: (1+2+3)*2 + (10+20)*3.
        ("Combos", "({1, 2, 3}) X, ({10, 20}) Y", "", "R", "0", "R + X + Y", {"p1": 102}),
        # ``distinct`` applies to the cross join: (1,1) and (2,1) are the two pairs.
        ("DistinctPairs", "({1, 2, 2}) X, ({1}) Y", "distinct", "R", "0", "R + 1", {"p1": 2}),
        # ``all`` (the default) keeps every pair, duplicates included.
        ("AllPairs", "({1, 2, 2}) X, ({1}) Y", "all", "R", "0", "R + 1", {"p1": 3}),
        # A scalar accumulator with another starting value: X occurs twice per pair.
        ("Product", "({1, 2, 3}) X, ({10, 20}) Y", "", "R", "1", "R * X", {"p1": 36}),
    ],
)
def test_multi_source_fold_content(define, sources, keyword, accumulator, start, body, expected):
    """The fold over several sources still folds every cross-joined row exactly once."""
    library = _multi_source(define, sources, keyword, accumulator, start, body)
    columns = {"Initial Population": "Initial Population", "Denominator": "Denominator",
               "Numerator": "Numerator", define: define}
    for con in _engines():
        sql = _translate(con, library, columns)
        con.execute("CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
                    "resource JSON, patient_ref VARCHAR)")
        con.execute(
            "INSERT INTO resources VALUES ('p1','Patient',?::JSON,'p1')",
            [json.dumps({"resourceType": "Patient", "id": "p1"})],
        )
        folds = _FOLD.findall(sql)
        assert len(folds) == 1, sql.count("WITH RECURSIVE")
        assert "__fold(__acc, __rn, __items, __c0, __c1) AS (" in folds[0], folds[0][:300]
        assert _column(con, sql, define) == expected


def test_integer_overflow_inside_a_fold_is_null():
    """The arithmetic overflow guard survives the rewrite: CQL overflow is null, not an error."""
    library = _multi_source(
        "Overflow", "({1}) X, ({1}) Y", "", "R", "9223372036854775807L", "R + X + Y"
    )
    columns = {"Initial Population": "Initial Population", "Denominator": "Denominator",
               "Numerator": "Numerator", "Overflow": "Overflow"}
    for con in _engines():
        sql = _translate(con, library, columns)
        assert "TRY(__fold.__acc + __fold.__c0)" in sql, sql[sql.index("UNION ALL") :][:300]
        con.execute("CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
                    "resource JSON, patient_ref VARCHAR)")
        con.execute(
            "INSERT INTO resources VALUES ('p1','Patient',?::JSON,'p1')",
            [json.dumps({"resourceType": "Patient", "id": "p1"})],
        )
        assert _column(con, sql, "Overflow") == {"p1": None}
