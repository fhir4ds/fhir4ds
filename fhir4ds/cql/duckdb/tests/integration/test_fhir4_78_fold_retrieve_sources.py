"""FHIR4-78 — a retrieve is a valid source of a multi-source aggregate.

`from [MedicationRequest] M, [Condition] C aggregate R starting 0: R + 1` folds over the
cross join of the patient's requests and conditions. The multi-source lowering wrapped every
non-list source in a single-element array, so a retrieve (a table, not a list) inside a fold
never resolved: a typed TranslationError in expression mode and an unresolved-placeholder
RuntimeError in population mode.

Values only, never lengths: NULL and a truncated list are both wrong answers.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import duckdb

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

#: (requests with their status, conditions) per patient.
_DATA = {
    "p1": ([("m1", "active"), ("m2", "cancelled")], ["c1"]),
    "p2": ([("m3", "active")], ["c2", "c3"]),
    "p3": ([], []),
}

_HEAD = """library F78 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Requests": [MedicationRequest]
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
        (pid, "Patient", {"resourceType": "Patient", "id": pid}, pid) for pid in _DATA
    ]
    for pid, (requests, conditions) in _DATA.items():
        rows += [
            (
                rid,
                "MedicationRequest",
                {
                    "resourceType": "MedicationRequest",
                    "id": rid,
                    "status": status,
                    "subject": {"reference": f"Patient/{pid}"},
                },
                pid,
            )
            for rid, status in requests
        ]
        rows += [
            (
                cid,
                "Condition",
                {
                    "resourceType": "Condition",
                    "id": cid,
                    "subject": {"reference": f"Patient/{pid}"},
                },
                pid,
            )
            for cid in conditions
        ]
    for rid, rtype, resource, pid in rows:
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [rid, rtype, json.dumps(resource), pid],
        )


def _fold_sql(con, query: str) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_HEAD + f'define "D": {query}\n')
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns={"Initial Population": "Initial Population", "D": "D"}
    )


def _fold(con, query: str) -> dict:
    sql = _fold_sql(con, query)
    assert "__f4ds_ph_" not in sql, "an unresolved fold marker leaked into the SQL"
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return {str(row[0]): row[names.index("D")] for row in cursor.fetchall()}


def _sortedlists(result: dict) -> dict:
    """Join order varies with the plan, so list answers compare as sets."""
    return {
        patient: sorted(values) if isinstance(values, list) else values
        for patient, values in result.items()
    }


def test_two_retrieves_cross_join_within_the_patient():
    query = "from [MedicationRequest] M, [Condition] C aggregate R starting 0: R + 1"
    for con in _engines():
        _load(con)
        assert _fold(con, query) == {"p1": 2, "p2": 2, "p3": 0}


def test_a_retrieve_beside_a_list_source():
    query = "from [MedicationRequest] M, ({1, 2}) X aggregate R starting 0: R + X"
    for con in _engines():
        _load(con)
        assert _fold(con, query) == {"p1": 6, "p2": 3, "p3": 0}


def test_the_elements_are_the_resources():
    query = (
        "from [MedicationRequest] M, [Condition] C aggregate R starting ({} as List<String>): "
        "R union {M.id & '|' & C.id}"
    )
    expected = {
        "p1": ["m1|c1", "m2|c1"],
        "p2": ["m3|c2", "m3|c3"],
        "p3": [],
    }
    for con in _engines():
        _load(con)
        assert _sortedlists(_fold(con, query)) == expected


def test_where_and_let_read_a_retrieve_source():
    # p1: one active request x two X values x (2 + 4); p2: the same with its one request.
    query = (
        "from [MedicationRequest] M, ({1, 2}) X where M.status = 'active' let N: X * 2 "
        "aggregate R starting 0: R + N"
    )
    for con in _engines():
        _load(con)
        assert _fold(con, query) == {"p1": 6, "p2": 6, "p3": 0}


def test_a_resource_rows_define_is_a_source_too():
    query = 'from "Requests" M, [Condition] C aggregate R starting 0: R + 1'
    for con in _engines():
        _load(con)
        assert _fold(con, query) == {"p1": 2, "p2": 2, "p3": 0}


def test_without_a_starting_value_and_with_distinct():
    for con in _engines():
        _load(con)
        no_start = "from [MedicationRequest] M, [Condition] C aggregate R: Coalesce(R, 0) + 1"
        assert _fold(con, no_start) == {"p1": 2, "p2": 2, "p3": None}
        distinct = (
            "from [MedicationRequest] M, ({1, 1}) X aggregate distinct R starting 0: R + 1"
        )
        assert _fold(con, distinct) == {"p1": 2, "p2": 1, "p3": 0}


def test_each_retrieve_source_is_the_patients_own_rows():
    """The lowering reads each retrieve patient-correlated, as the single-source fold does."""
    query = "from [MedicationRequest] M, [Condition] C aggregate R starting 0: R + 1"
    for con in _engines():
        _load(con)
        sql = _fold_sql(con, query)
        assert (
            'FROM "MedicationRequest" AS __ms0 WHERE __ms0.patient_id = _pt.patient_id'
            in sql
        ), sql[sql.index("WITH RECURSIVE") :][:900]
        assert 'FROM "Condition" AS __ms1 WHERE __ms1.patient_id = _pt.patient_id' in sql
        # A retrieve is a table, never a single-element array of a table reference.
        assert 'unnest(["MedicationRequest"]' not in sql
