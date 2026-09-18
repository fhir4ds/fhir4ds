"""coding_matches / coding_matches_exact native C++ parity (v0.0.14).

The C++ ports must be byte-equivalent to the Python supplements
(fhir4ds/cql/duckdb/udf/valueset.py codingMatches/codingMatchesExact)
across native-loaded, forced-Python, and no-Python/browser-style legs,
including system normalization (OID aliases, SNOMED module URLs,
QICoreCommon shorthand aliases) and exact-match display/version
absence semantics (CQL Equal on Code).
"""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements

from .wasm_runtime_helpers import no_python_connection


OBS_RESOURCE = json.dumps(
    {
        "resourceType": "Observation",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8480-6", "display": "BP"},
                {"system": "urn:oid:2.16.840.1.113883.6.96", "code": "S1"},
                {"system": "http://snomed.info/sct/731000124108", "code": "S2", "version": "v1"},
            ]
        },
        "valueCodeableConcept": {
            "coding": [
                {"system": "http://snomed.info/sct", "code": "X1", "display": "ex", "version": "2"}
            ]
        },
    }
)

CONCEPT_ELEMENT = json.dumps({"coding": [{"system": "http://loinc.org", "code": "L1"}]})

# (resource, path, system, code, expected)
MATCH_CASES = [
    (OBS_RESOURCE, "code", "http://loinc.org", "8480-6", True),
    (OBS_RESOURCE, "code", "LOINC", "8480-6", True),
    (OBS_RESOURCE, "code", "urn:oid:2.16.840.1.113883.6.1", "8480-6", True),
    # OID-form system on the resource matches canonical literal
    (OBS_RESOURCE, "code", "http://snomed.info/sct", "S1", True),
    # SNOMED module URL normalizes to base
    (OBS_RESOURCE, "code", "http://snomed.info/sct", "S2", True),
    (OBS_RESOURCE, "code", "http://loinc.org", "9999", False),
    (OBS_RESOURCE, "valueCodeableConcept", "http://snomed.info/sct", "X1", True),
    (CONCEPT_ELEMENT, "code", "http://loinc.org", "L1", True),
    ("not json", "code", "s", "c", None),
    (OBS_RESOURCE, "", "http://loinc.org", "L1", None),
    (OBS_RESOURCE, "code", "http://loinc.org", "", None),
]

# (resource, path, system, code, display, version, expected)
EXACT_CASES = [
    (OBS_RESOURCE, "code", "http://loinc.org", "8480-6", "BP", None, True),
    # literal display absent -> coding must not carry one
    (OBS_RESOURCE, "code", "http://loinc.org", "8480-6", None, None, False),
    (OBS_RESOURCE, "code", "http://loinc.org", "8480-6", "WRONG", None, False),
    (OBS_RESOURCE, "code", "http://snomed.info/sct", "S2", None, "v1", True),
    (OBS_RESOURCE, "code", "http://snomed.info/sct", "S2", None, None, False),
    (OBS_RESOURCE, "valueCodeableConcept", "http://snomed.info/sct", "X1", "ex", "2", True),
    (OBS_RESOURCE, "valueCodeableConcept", "http://snomed.info/sct", "X1", "ex", None, False),
    (OBS_RESOURCE, "valueCodeableConcept", "http://snomed.info/sct", "X1", None, "2", False),
    (CONCEPT_ELEMENT, "code", "LOINC", "L1", None, None, True),
]


def _assert_identity(con: duckdb.DuckDBPyConnection, label: str, name: str) -> None:
    rows = con.execute(
        "SELECT function_name, function_type FROM duckdb_functions() "
        "WHERE lower(function_name) = ?",
        [name.lower()],
    ).fetchall()
    assert rows, f"{label}: {name} is not registered"
    for _, ftype in rows:
        assert ftype == "scalar", f"{label}: {name} is {ftype}, expected scalar"


@pytest.mark.parametrize(
    "resource,path,system,code,expected",
    MATCH_CASES,
)
def test_coding_matches_three_leg_parity(resource, path, system, code, expected) -> None:
    sql = "SELECT coding_matches(?, ?, ?, ?)"
    params_none = resource is None or not path or not code

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    try:
        register(native, include_fhirpath=False)
        _assert_identity(native, "native", "coding_matches")
        got = native.execute(sql, [resource, path, system, code]).fetchone()[0]
    finally:
        native.close()
    assert got == expected, f"native coding_matches({path!r}, {system!r}, {code!r}) = {got!r}, want {expected!r}"

    py = duckdb.connect()
    try:
        _register_python_supplements(py, cpp_loaded=False, include_fhirpath=False)
        got = py.execute(sql, [resource, path, system, code]).fetchone()[0]
    finally:
        py.close()
    assert got == expected, f"python coding_matches({path!r}, {system!r}, {code!r}) = {got!r}, want {expected!r}"

    if params_none:
        return  # NULL/empty params may bind differently on the no-Python leg
    with no_python_connection() as nopy:
        _assert_identity(nopy, "no-python", "coding_matches")
        got = nopy.execute(sql, [resource, path, system, code]).fetchone()[0]
    assert got == expected, f"no-python coding_matches({path!r}, {system!r}, {code!r}) = {got!r}, want {expected!r}"


@pytest.mark.parametrize(
    "resource,path,system,code,display,version,expected",
    EXACT_CASES,
)
def test_coding_matches_exact_three_leg_parity(
    resource, path, system, code, display, version, expected
) -> None:
    sql = "SELECT coding_matches_exact(?, ?, ?, ?, ?, ?)"

    def run(con: duckdb.DuckDBPyConnection) -> object:
        return con.execute(sql, [resource, path, system, code, display, version]).fetchone()[0]

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    try:
        register(native, include_fhirpath=False)
        _assert_identity(native, "native", "coding_matches_exact")
        got = run(native)
    finally:
        native.close()
    assert got == expected, f"native exact = {got!r}, want {expected!r}"

    py = duckdb.connect()
    try:
        _register_python_supplements(py, cpp_loaded=False, include_fhirpath=False)
        got = run(py)
    finally:
        py.close()
    assert got == expected, f"python exact = {got!r}, want {expected!r}"

    with no_python_connection() as nopy:
        _assert_identity(nopy, "no-python", "coding_matches_exact")
        got = run(nopy)
    assert got == expected, f"no-python exact = {got!r}, want {expected!r}"


DYNAMIC_LIBRARY = """
library CodingMatchFeature version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
code "Systolic": '8480-6' from LOINC display 'Systolic blood pressure'
context Patient
define "SystolicObs": exists ([Observation] O where O.code ~ "Systolic")
define "SystolicObsExact": exists ([Observation] O where O.code = "Systolic")
"""


def test_coding_matches_translated_no_python_runtime() -> None:
    """End-to-end: translated population SQL over the C++ functions."""
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql

    translated = translate_cql(DYNAMIC_LIBRARY)
    population_sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(DYNAMIC_LIBRARY),
        output_columns={"SystolicObs": "SystolicObs", "SystolicObsExact": "SystolicObsExact"},
    )
    patient = json.dumps({"resourceType": "Patient", "id": "p1"})
    observation = json.dumps(
        {
            "resourceType": "Observation",
            "id": "o1",
            "subject": {"reference": "Patient/p1"},
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "8480-6",
                        "display": "Systolic blood pressure",
                    }
                ]
            },
        }
    )
    with no_python_connection() as con:
        con.execute("INSERT INTO resources VALUES (?, 'Patient', ?::JSON, 'p1')", ["p1", patient])
        con.execute("INSERT INTO resources VALUES (?, 'Observation', ?::JSON, 'p1')", ["o1", observation])
        row = con.execute(population_sql).fetchone()
        assert row == ("p1", True, True), f"expected (p1, True, True), got {row!r}"
        for name in ("SystolicObs", "SystolicObsExact"):
            sql = translated[name].to_sql()
            assert "coding_matches" in sql, f"{name} must lower through coding_matches"
