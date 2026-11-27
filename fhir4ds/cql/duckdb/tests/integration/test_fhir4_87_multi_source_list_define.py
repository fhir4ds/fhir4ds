"""FHIR4-87 — a LIST-valued define is one source of a multi-source aggregate per ELEMENT.

    define "L": {10, 20, 30}
    define "R": from "L" N, [Condition] C aggregate A starting 0: A + 1

The cross join is three elements by the patient's conditions. The lowering wrapped the
define's list as ONE element (``unnest([(SELECT * FROM "L")])``) or read it as a rows table,
so the fold ran once per patient instead of once per element — a plausible number over the
wrong multiplicity, which is worse than a binder error.

The referee asserts the ITERATED number and asserts it differs from the once-per-patient
number, so the test cannot pass by luck. The inlined-list form is pinned beside it as the
control it must agree with (FHIR4-78 made a rows-shaped source contribute its resources the
same way).
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import duckdb

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

#: p1: 2 conditions, 2 given names. p2: 1 condition, 1 given name. p3: nothing.
_DATA = {
    "p1": (["A", "B"], ["c1", "c2"]),
    "p2": (["C"], ["c3"]),
    "p3": ([], []),
}

_LIST = 'define "L": {10, 20, 30}\n'
_NAMES = 'define "L": Patient.name.given\n'
_ELEMENT_QUERY = 'define "L": [Condition] C return C.id\n'

_HEAD = """library F87 version '1.0.0'
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
    """Python supplements and the C++-only engine: the lowering must hold on both."""
    for build in (_python_connection, no_python_connection):
        with build() as con:
            yield con


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    rows = [
        (
            pid,
            "Patient",
            {"resourceType": "Patient", "id": pid, "name": [{"given": names}]},
            pid,
        )
        for pid, (names, _) in _DATA.items()
    ]
    for pid, (_, conditions) in _DATA.items():
        rows += [
            (
                cid,
                "Condition",
                {"resourceType": "Condition", "id": cid, "subject": {"reference": f"Patient/{pid}"}},
                pid,
            )
            for cid in conditions
        ]
    for rid, rtype, resource, pid in rows:
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [rid, rtype, json.dumps(resource), pid],
        )


def _fold(con, definitions: str, query: str) -> dict:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_HEAD + definitions + f'define "D": {query}\n')
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(
        library=library,
        output_columns={"Initial Population": "Initial Population", "D": "D"},
    )
    assert "__f4ds_ph_" not in sql, "an unresolved fold marker leaked into the SQL"
    _load(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return {str(row[0]): row[names.index("D")] for row in cursor.fetchall()}


def test_the_referee_a_three_element_define_times_the_patients_rows():
    """3 elements x the patient's conditions — NOT once per patient."""
    query = 'from "L" N, [Condition] C aggregate A starting 0: A + 1'
    inline = "from ({10, 20, 30}) N, [Condition] C aggregate A starting 0: A + 1"
    for con in _engines():
        answered = _fold(con, _LIST, query)
        assert answered == {"p1": 6, "p2": 3, "p3": 0}, answered
        # The wrong-multiplicity answer is one pair per patient per source element bucket.
        assert answered["p1"] != 2, "the define's list was wrapped as a single element"
        assert answered["p2"] != 1, "the define's list was wrapped as a single element"
        # …and the fold agrees with the inlined list, which was never broken.
        assert answered == _fold(con, "", inline)


def test_the_list_define_may_be_the_second_source():
    query = 'from [Condition] C, "L" N aggregate A starting 0: A + 1'
    for con in _engines():
        assert _fold(con, _LIST, query) == {"p1": 6, "p2": 3, "p3": 0}


def test_a_navigation_define_contributes_its_own_elements():
    """p1 has two given names and two conditions, p2 one of each, p3 none."""
    query = 'from "L" N, [Condition] C aggregate A starting 0: A + 1'
    for con in _engines():
        answered = _fold(con, _NAMES, query)
        assert answered == {"p1": 4, "p2": 1, "p3": 0}, answered
        assert answered["p1"] != 2, "the navigation list was wrapped as a single element"


def test_a_value_rows_query_define_contributes_its_rows():
    """A query define of one value row per element is a source of the same arity."""
    query = 'from "L" N, [Condition] C aggregate A starting 0: A + 1'
    for con in _engines():
        assert _fold(con, _ELEMENT_QUERY, query) == {"p1": 4, "p2": 1, "p3": 0}


def test_where_filters_the_defines_elements():
    # One element (30) survives the filter, so p1 folds its two conditions once.
    query = 'from "L" N, [Condition] C where N > 25 aggregate A starting 0: A + 1'
    inline = "from ({10, 20, 30}) N, [Condition] C where N > 25 aggregate A starting 0: A + 1"
    for con in _engines():
        answered = _fold(con, _LIST, query)
        assert answered == {"p1": 2, "p2": 1, "p3": 0}, answered
        assert answered == _fold(con, "", inline)


def test_let_reads_the_defines_elements():
    query = 'from "L" N, [Condition] C let P: N * 2 aggregate A starting 0: A + P'
    inline = "from ({10, 20, 30}) N, [Condition] C let P: N * 2 aggregate A starting 0: A + P"
    for con in _engines():
        # p1: two conditions x (20 + 40 + 60) = 240; p2: one condition x the same = 120.
        answered = _fold(con, _LIST, query)
        assert answered == {"p1": 240, "p2": 120, "p3": 0}, answered
        assert answered == _fold(con, "", inline)
