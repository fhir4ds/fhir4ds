"""FHIR4-96 — a multi-source QUERY over LIST sources must iterate ELEMENTS.

``from ({1, 2, 3}) A, ({4, 5, 6}) B return A * 10 + B`` is the plainest multi-source query
there is, and it did not run at all: ``Binder Error: Table "A" does not have a column named
"patient_id"``. Three layers each assumed a source is a ROW table:

1. ``_query._translate_query``'s multi-source branch put the unnested source in the FROM as
   ``unnest([1, 2, 3]) AS A``. In DuckDB that makes ``A`` a STRUCT(unnest INTEGER), not the
   element — so even ``where A > 1`` failed with ``Cannot compare values of type STRUCT(unnest
   INTEGER)``. Its sibling (the no-return tuple branch) already wrapped the same source as
   ``(SELECT unnest AS A FROM unnest(...))``, which is the shape every alias reference needs.
2. the alias was registered WITHOUT its source AST, so ``A + B`` read ``B.resource`` (a row
   column) instead of the element; the PRIMARY source was registered with its AST and read
   ``A`` correctly, which is why the two aliases of one query disagreed.
3. ``CTEManager._add_patient_id`` took patient_id from ``<first source alias>.patient_id``. A
   list source has no such column, so the definition CTE must cross-join ``_patients`` and
   project ``_pt.patient_id`` — the doctrine already used for the ``_lt_unnest`` shape.

A LIST-valued DEFINE (``define "A2": {1, 2, 3}``) as a source had the mirror defect: its CTE
is ONE ROW holding the WHOLE list, so ``from "A2" A, "B2" B return A * 10 + B`` folded two
rows and answered the CONCATENATED list ``[1, 2, 3, 4, 5, 6]`` — a plausible number over the
wrong multiplicity, which is worse than a binder error (FHIR4-86/87 doctrine: the shape comes
from ``DefinitionMeta``, never from the SQL text).

The referee asserts the CROSS PRODUCT as a multiset and asserts it differs from the elementwise
and single-row answers, so the test cannot pass by luck. Lists are compared as multisets: a
multi-row define's list is materialised per consumer and ``list()`` over an unordered source
may return any permutation (FHIR4-109).
"""

from __future__ import annotations

import json
from collections import Counter
from contextlib import contextmanager

import duckdb

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

#: p1 has two conditions, p2 one, p3 none — so a patient-correlated answer is distinguishable
#: from an uncorrelated one.
_CONDITIONS = {"p1": ["c1", "c2"], "p2": ["c3"], "p3": []}

_HEAD = """library F96 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
"""

_LISTS = 'define "A2": {1, 2, 3}\ndefine "B2": {4, 5, 6}\n'

#: A*10+B over 1..3 x 4..6 — nine values, all distinct, and no value in the elementwise
#: (3) or single-row (1) answers.
_CROSS = [14, 15, 16, 24, 25, 26, 34, 35, 36]


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


def _result(con, definitions: str, query: str):
    """The define's own column, translated by this tree and executed."""
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_HEAD + definitions + f'define "D": {query}\n')
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(
        library=library,
        output_columns={"Initial Population": "Initial Population", "D": "D"},
    )
    _load(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return {str(row[0]): row[names.index("D")] for row in cursor.fetchall()}


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


def test_a_multi_source_query_over_list_literals_runs_and_crosses():
    """The card's repro: it must run, and it must be a CROSS PRODUCT of elements."""
    for con in _engines():
        answered = _result(con, "", "from ({1, 2, 3}) A, ({4, 5, 6}) B return A * 10 + B")
        assert set(answered) == set(_CONDITIONS), answered
        for pid in _CONDITIONS:
            elements = _elements(answered[pid], pid)
            assert elements == Counter(str(value) for value in _CROSS), (pid, elements)
            assert len(elements) == 9, f"{pid}: {len(elements)} elements, not 9"


def test_the_where_clause_filters_the_elements_not_a_row_struct():
    """`where A > 1` compares the ELEMENT: it used to binder-fail on STRUCT(unnest INTEGER)."""
    for con in _engines():
        answered = _result(
            con, "", "from ({1, 2, 3}) A, ({4, 5, 6}) B where A > 1 return A * 10 + B"
        )
        for pid in _CONDITIONS:
            elements = _elements(answered[pid], pid)
            assert elements == Counter(["24", "25", "26", "34", "35", "36"]), (pid, elements)


def test_a_stored_list_define_contributes_its_elements():
    """A list define is N elements, not one row holding the list (FHIR4-87's doctrine)."""
    for con in _engines():
        answered = _result(con, _LISTS, 'from "A2" A, "B2" B return A * 10 + B')
        for pid in _CONDITIONS:
            elements = _elements(answered[pid], pid)
            assert elements == Counter(str(value) for value in _CROSS), (pid, elements)
            # The wrong-multiplicity answer was the two lists concatenated.
            assert elements != Counter(["1", "2", "3", "4", "5", "6"]), (
                pid,
                "the stored list was read as ONE row",
            )


def test_a_list_define_and_a_list_literal_agree():
    """Mixed sources take the same path; the inline literal is the control."""
    for con in _engines():
        mixed = _result(con, _LISTS, 'from "A2" A, ({4, 5, 6}) B return A * 10 + B')
        inline = _result(con, "", "from ({1, 2, 3}) A, ({4, 5, 6}) B return A * 10 + B")
        for pid in _CONDITIONS:
            assert _elements(mixed[pid], pid) == _elements(inline[pid], pid), pid


def test_a_list_source_pairs_with_a_rows_source_per_patient():
    """p1 (2 conditions) x 2 elements = 4; p3 (no conditions) = none.

    ``return all`` keeps the tuples so the MULTIPLICITY is asserted; a plain ``return`` would
    de-duplicate the two elements and only emptiness would survive. The expression form is used
    because a bare ALIAS return of an element source (``return all N``) is still lowered to a
    scalar subquery — that is the FHIR4-92 shape ("a multi-row nested query as the single `from`
    source is lowered to a scalar subquery"), whose root is elsewhere and is not fixed here.
    """
    for con in _engines():
        answered = _result(con, "", "from ({10, 20}) N, [Condition] C return all N * 10")
        assert _elements(answered["p1"], "p1") == Counter({"100": 2, "200": 2})
        assert _elements(answered["p2"], "p2") == Counter({"100": 1, "200": 1})
        assert _elements(answered["p3"], "p3") == Counter()


def test_a_multi_source_query_without_a_return_clause_still_yields_tuples():
    """The tuple branch was already correct — it is the CONTROL for the element shape."""
    for con in _engines():
        answered = _result(con, "", "from ({1, 2, 3}) A, ({4, 5, 6}) B")
        expected = Counter(
            json.dumps({"A": str(a), "B": str(b)}, sort_keys=True, separators=(",", ":"))
            for a in (1, 2, 3)
            for b in (4, 5, 6)
        )
        for pid in _CONDITIONS:
            assert _elements(answered[pid], pid) == expected, pid
