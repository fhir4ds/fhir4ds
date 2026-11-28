"""FHIR4-97 — a nested INLINE query as the single fold source correlates to the wrong alias.

    define "D": ([Condition] C return C.id) X aggregate Acc starting 0: Acc + 1

answered ``Binder Error: Referenced table "X" not found!`` on both the desktop engine and real
duckdb-wasm. ``X`` is the QUERY alias, which names the query's RESULT; inside the fold's element
list there is no ``X`` in scope at all. The correlation belongs to the alias that supplies the
ROWS — the inner retrieve's ``C``:

    -- before (fold source)
    (SELECT COALESCE(list(_cql_list_source.__cql_list_value), []) FROM (
        SELECT fhirpath_text(C.resource, 'id') AS __cql_list_value
        FROM "Condition" AS C WHERE X.patient_id = _pt.patient_id) AS _cql_list_source)
    -- after
    ... WHERE C.patient_id = _pt.patient_id ...

``_query._translate_query``'s rows-to-list coercion correlates the PROJECTED select (correct —
that is where the row alias binds) but passed the fold's own ``_row_alias``, which defaults to the
query alias. A source whose inner query supplies rows under a DIFFERENT alias therefore produced
a predicate on an alias that does not exist. The sibling branch for multi-column rows already
takes the alias from ``from_clause``; this one now does too.

The defect is narrower than "any nested query" — it needs the fold source to be a query that
projects a VALUE. The same query as a named define (``define "Q": (...)`` then ``"Q" X
aggregate ...``) always worked, and it is the referee below: the inline form must answer what the
named form answers. Counts are asserted per patient (3 patients, 2/1/0 conditions), so an
uncorrelated fold (every patient counting all rows) and a dropped fold (0) both fail.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_CONDITIONS = {"p1": ["c1", "c2"], "p2": ["c3"], "p3": []}

_HEAD = """library F97 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
"""

_INLINE = "([Condition] C return C.id) X aggregate Acc starting 0: Acc + 1"
_NAMED = '"Q" X aggregate Acc starting 0: Acc + 1'
_NAMED_DEFINITION = 'define "Q": ([Condition] C return C.id)\n'


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
    for build in (_python_connection, no_python_connection):
        with build() as con:
            yield con


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    for pid, conditions in _CONDITIONS.items():
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [pid, "Patient", json.dumps({"resourceType": "Patient", "id": pid}), pid],
        )
        for cid in conditions:
            con.execute(
                "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                [
                    cid,
                    "Condition",
                    json.dumps(
                        {
                            "resourceType": "Condition",
                            "id": cid,
                            "subject": {"reference": f"Patient/{pid}"},
                        }
                    ),
                    pid,
                ],
            )


def _sql_for(con, definitions: str, expression: str) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_HEAD + definitions + f'define "D": {expression}\n')
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library,
        output_columns={"Initial Population": "Initial Population", "D": "D"},
    )


def _result(con, definitions: str, expression: str) -> dict:
    sql = _sql_for(con, definitions, expression)
    _load(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return {str(row[0]): row[names.index("D")] for row in cursor.fetchall()}


def test_an_inline_query_as_the_single_fold_source_runs():
    """2/1/0 conditions: the fold counts THIS patient's elements, once each."""
    for con in _engines():
        answered = _result(con, "", _INLINE)
        assert answered == {"p1": 2, "p2": 1, "p3": 0}, answered


def test_the_inline_form_answers_what_the_named_form_answers():
    """The named define was never broken; it is the referee for the inline form."""
    for con in _engines():
        assert _result(con, "", _INLINE) == _result(con, _NAMED_DEFINITION, _NAMED)


def test_a_where_clause_over_the_inline_query_filters_the_fold():
    for con in _engines():
        answered = _result(
            con, "", "([Condition] C return C.id) X where X = 'c1' aggregate Acc starting 0: Acc + 1"
        )
        assert answered == {"p1": 1, "p2": 0, "p3": 0}, answered


def test_a_let_clause_over_the_inline_query_runs():
    for con in _engines():
        answered = _result(
            con,
            "",
            "([Condition] C return C.id) X let Y: X aggregate Acc starting 0: Acc + 1",
        )
        assert answered == {"p1": 2, "p2": 1, "p3": 0}, answered


def test_the_correlation_names_the_alias_that_supplies_the_rows():
    """Shape assertion: the fold source predicate is on the RETRIEVE alias, never the query alias."""
    for con in _engines():
        sql = _sql_for(con, "", _INLINE)
        assert "X.patient_id" not in sql, "the correlation names the query alias, which is not in scope"
        assert "C.patient_id = _pt.patient_id" in sql, "the fold source is not patient-correlated"


def test_a_retrieve_fold_keeps_its_existing_correlation():
    """The control: a bare retrieve source was, and stays, correlated to its own alias."""
    for con in _engines():
        assert _result(con, "", "[Condition] C aggregate Acc starting 0: Acc + 1") == {
            "p1": 2,
            "p2": 1,
            "p3": 0,
        }
