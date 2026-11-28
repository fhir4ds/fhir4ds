"""FHIR4-92 — a list-valued query DEFINE is a LIST, not one scalar value.

``define "Result": from ({3, 1, 2}) D return D`` is a three-element CQL value. It translated
to a SCALAR CTE:

    "Result" AS MATERIALIZED (
      SELECT _pt.patient_id,
             (SELECT D FROM (SELECT unnest([3, 1, 2]) AS D) AS _list) AS value
      FROM _patients AS _pt )

and died at execution with ``More than one row returned by a subquery used as an expression``.
The tell is a metadata CONTRADICTION the translator produced itself: the define was classified
``RowShape.PATIENT_SCALAR`` while its ``cql_type`` was ``List<Integer>``. One row per patient
cannot hold a three-element list as "the value" unless the value IS a list, and the scalar path
does not aggregate.

The same query with an EXPRESSION return was correct
(``return all D * 10`` → ``PATIENT_MULTI_VALUE``, one row per element), so the difference was
never "a nested query source" — it was the bare-alias RETURN (the bare ``return all D`` form was
broken too). Root cause: ``_infer_row_shape``'s query branch inherited the shape of a
bare-alias source expression, and a LIST source is classified ``PATIENT_SCALAR`` (a list literal
is one value per patient). But a query source binds its alias to ONE ELEMENT at a time
(CQL 1.5 §Query), so ``return <alias>`` over a list source is one row per ELEMENT.

ORDER IS NOT PART OF THE CONTRACT (FHIR4-109): a multi-row define's list is materialised per
consumer and ``list()`` over an unordered source may return any permutation. Every assertion
below compares MULTISETS.
"""

from __future__ import annotations

import json
from collections import Counter
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

#: p1 has two conditions, p2 one, p3 none — so a patient-correlated answer is distinguishable
#: from an uncorrelated one.
_CONDITIONS = {"p1": ["c1", "c2"], "p2": ["c3"], "p3": []}

_CONDITION_ELEMENTS = {"p1": 2, "p2": 1, "p3": 0}

_HEAD = """library F92 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
"""


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


def _translate(con, definitions: str, query: str):
    """Translate one define; return (sql, shape, cql_type)."""
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_HEAD + definitions + f'define "Result": {query}\n')
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(
        library=library,
        output_columns={"Initial Population": "Initial Population", "Result": "Result"},
    )
    meta = translator._context.definition_meta["Result"]
    return sql, meta.shape, getattr(meta, "cql_type", None)


def _result(con, definitions: str, query: str):
    """The define's own column, translated by this tree and executed."""
    sql, _shape, _cql_type = _translate(con, definitions, query)
    _load(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return {str(row[0]): row[names.index("Result")] for row in cursor.fetchall()}


def _results(con, definitions: str, consumers: dict[str, str]) -> dict[str, dict]:
    """Several consumer defines over *definitions*, as {name: {patient: value}}."""
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    body = definitions + "".join(f'define "{n}": {e}\n' for n, e in consumers.items())
    library = parse_cql(_HEAD + body)
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(
        library=library,
        output_columns={"Initial Population": "Initial Population", **{n: n for n in consumers}},
    )
    _load(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    return {n: {str(r["patient_id"]): r[n] for r in rows} for n in consumers}


def _elements(value, pid: str) -> Counter:
    """The define's list as a multiset of elements (order is not part of the contract)."""
    assert value is not None, f"{pid}: the define answered NULL, so the query did not run"
    items = json.loads(value) if isinstance(value, str) else value
    if not isinstance(items, list):
        items = [items]
    return Counter(
        json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
        for item in items
    )


class TestABareAliasReturnOverAListSourceIsAList:
    def test_a_nested_list_literal_query_answers_all_three_elements(self):
        """The card's repro: it used to raise `More than one row returned by a subquery`."""
        for con in _engines():
            answered = _result(con, "", "from ({3, 1, 2}) D return D")
            assert set(answered) == set(_CONDITIONS), answered
            for pid in _CONDITIONS:
                assert _elements(answered[pid], pid) == Counter(["1", "2", "3"]), pid

    def test_a_where_clause_filters_the_elements(self):
        """`where D > 1` prunes the element rows, not a single scalar."""
        for con in _engines():
            answered = _result(con, "", "from ({3, 1, 2}) D where D > 1 return D")
            for pid in _CONDITIONS:
                assert _elements(answered[pid], pid) == Counter(["2", "3"]), pid

    def test_the_metadata_and_the_sql_agree_that_the_define_is_a_list(self):
        """The contradiction under test: `List<Integer>` + PATIENT_SCALAR + no aggregate.

        A PATIENT_SCALAR define may perfectly well hold a list — but then its value column
        must AGGREGATE the rows into that list, and the broken tree did not: it emitted a
        single-row scalar subquery (`(SELECT D FROM (SELECT unnest(…) AS D) AS _list)`) for a
        define whose type said three elements. Asserting the SHAPE alone cannot see that (the
        broken tree already answered PATIENT_SCALAR), so this pins the SQL SHAPE the chosen
        representation demands.
        """
        for con in _engines():
            sql, shape, cql_type = _translate(con, "", "from ({3, 1, 2}) D return D")
            assert cql_type == "List<Integer>", cql_type
            # One row per ELEMENT (the `return all` twin's shape, and the element-rows
            # doctrine CQL-19 established for every query define).
            assert shape.name == "PATIENT_MULTI_VALUE", shape
            assert "SELECT _pt.patient_id, D AS value FROM (SELECT unnest([3, 1, 2]) AS D)" in sql, sql
            # The scalar-subquery form that produced the card's error must be gone.
            assert "(SELECT D FROM (SELECT unnest(" not in sql, sql
            _load(con)
            answered = con.execute(sql).fetchall()
            assert len(answered) == len(_CONDITIONS), answered


class TestControlFormsStillWork:
    def test_return_all_expression_form_is_unchanged(self):
        """The control the card names: `return all D * 10` already worked."""
        for con in _engines():
            answered = _result(con, "", "from ({3, 1, 2}) D return all D * 10")
            for pid in _CONDITIONS:
                assert _elements(answered[pid], pid) == Counter(["10", "20", "30"]), pid

    def test_a_stored_list_define_source_answers_its_elements(self):
        """`from "A2" B return B` — the same defect through a DEFINE rather than a literal."""
        for con in _engines():
            answered = _result(con, 'define "A2": {3, 1, 2}\n', 'from "A2" B return B')
            for pid in _CONDITIONS:
                assert _elements(answered[pid], pid) == Counter(["1", "2", "3"]), pid

    def test_a_per_patient_list_source_keeps_its_multiplicity(self):
        """FHIR4-96's per-patient neighbour with a BARE alias return (it raised too).

        p1 has two conditions, so `{10, 20} x {c1, c2}` is four tuples; `return all` keeps
        them (a plain `return` would de-duplicate to two elements).
        """
        for con in _engines():
            answered = _result(con, "", "from ({10, 20}) N, [Condition] C return all N")
            assert set(answered) == set(_CONDITIONS), answered
            for pid, count in _CONDITION_ELEMENTS.items():
                expected = Counter({"10": count, "20": count}) if count else Counter()
                assert _elements(answered[pid], pid) == expected, (pid, count)


class TestMembershipOverTheListSource:
    def test_membership_tests_every_element(self):
        """`in` / `contains` over the define must test the WHOLE list.

        The generic LIST translation of an element-rows define can be a list built AROUND a
        `LIMIT 1` scalar lookup — one element wearing a list's clothes. The SQL-shape test
        accepted that and short-circuited the element-rows gate, so `2 in <{3,1,2}>`
        answered FALSE (before the shape fix it raised, so the regression would have been a
        silent wrong answer). The gate now runs BEFORE the shape test.
        """
        consumers = {
            "InTwo": '2 in "Nums"',
            "NotIn": '9 in "Nums"',
            "ContainsTwo": '"Nums" contains 2',
            "ContainsThree": '"Nums" contains 3',
        }
        expected = {"InTwo": True, "NotIn": False, "ContainsTwo": True, "ContainsThree": True}
        for con in _engines():
            answered = _results(con, 'define "Nums": from ({3, 1, 2}) D return D\n', consumers)
            for name, want in expected.items():
                for pid in _CONDITIONS:
                    assert answered[name][pid] is want, (name, pid, answered[name][pid])


class TestReturnDuplicatesAreNotCollapsed:
    def test_return_all_keeps_duplicate_elements(self):
        """`return all` keeps every element row, duplicates included."""
        for con in _engines():
            kept = _result(con, "", "from ({3, 1, 3, 2}) D return all D")
            for pid in _CONDITIONS:
                assert _elements(kept[pid], pid) == Counter(["1", "2", "3", "3"]), pid

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "PRE-EXISTING and separate from FHIR4-92: implicit `return` de-duplication never "
            "fires for ANY query-form definition. The parser wraps a definition body that is "
            "a query in an outer single-source Query, so `_return_clause_is_distinct`'s "
            "`root_ast is node` test is false for the inner query that actually carries the "
            "return clause — `define R: ([Condition] C return C.status) X` keeps duplicate "
            "statuses today as well, on a shape this card never touched. Deliberately NOT "
            "fixed here: the FHIR4-136 doctrine makes root-scoping load-bearing, and turning "
            "it on for every query define changes corpus SQL."
        ),
    )
    def test_a_plain_return_over_a_list_source_de_duplicates(self):
        """CQL 1.5 §Query: a plain `return` eliminates duplicate results."""
        for con in _engines():
            deduped = _result(con, "", "from ({3, 1, 3, 2}) D return D")
            for pid in _CONDITIONS:
                assert _elements(deduped[pid], pid) == Counter(["1", "2", "3"]), pid
