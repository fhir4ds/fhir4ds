"""CQL clinical type parser and DuckDB valueset parity checks."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    con.remove_function("in_valueset")
    con.create_function(
        "in_valueset",
        createValuesetMembershipUdf(
            {
                "http://example.org/fhir/ValueSet/vitals": {
                    ("http://loinc.org", "8867-4"),
                    ("", "code-only"),
                }
            }
        ),
        null_handling="special",
    )
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    con.execute("SELECT cql_valueset_cache_clear()")
    con.execute(
        "SELECT cql_valueset_cache_add(?, ?, ?)",
        ["http://example.org/fhir/ValueSet/vitals", "http://loinc.org", "8867-4"],
    )
    con.execute(
        "SELECT cql_valueset_cache_add(?, ?, ?)",
        ["http://example.org/fhir/ValueSet/vitals", "", "code-only"],
    )
    return con


def test_cql_clinical_definitions_parse_and_translate() -> None:
    cql = """library Clinical version '1.0.0'
using FHIR version '4.0.1'
codesystem "LOINC": 'http://loinc.org' version '2.74'
valueset "Vitals": 'http://example.org/fhir/ValueSet/vitals'
code "Heart Rate": '8867-4' from "LOINC" display 'Heart rate'
concept "Vital Concept": { "Heart Rate" } display 'Vitals'
context Patient
define "Code Literal": Code '8867-4' from "LOINC" display 'Heart rate'
"""

    library = parse_cql(cql)
    assert library.codesystems[0].name == "LOINC"
    assert library.codesystems[0].id == "http://loinc.org"
    assert library.valuesets[0].name == "Vitals"
    assert library.codes[0].name == "Heart Rate"
    assert library.concepts[0].name == "Vital Concept"
    assert library.concepts[0].codes == ["Heart Rate"]

    translated = translate_cql(cql)
    assert "http://loinc.org|8867-4" in str(translated["Code Literal"])


def test_cql_valueset_duckdb_surface_matches_cpp_registration() -> None:
    observation = json.dumps(
        {
            "resourceType": "Observation",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "8867-4",
                        "display": "Heart rate",
                    }
                ],
                "text": "Heart rate",
            },
        }
    )
    code_only = json.dumps(
        {
            "resourceType": "Observation",
            "code": {"coding": [{"code": "code-only"}]},
        }
    )
    profile = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"
    valueset = "http://example.org/fhir/ValueSet/vitals"

    expressions = [
        ("SELECT extractCodes(?, 'code')", [observation]),
        ("SELECT extractFirstCode(?, 'code')", [observation]),
        ("SELECT extractFirstCodeSystem(?, 'code')", [observation]),
        ("SELECT extractFirstCodeValue(?, 'code')", [observation]),
        ("SELECT resolveProfileUrl(?)", [profile]),
        ("SELECT in_valueset(?, 'code', ?)", [observation, valueset]),
        ("SELECT in_valueset(?, 'code', ?)", [code_only, valueset]),
        ("SELECT in_valueset(?, 'code', ?)", [observation, "http://example.org/missing"]),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, params in expressions:
            assert cpp.execute(sql, params).fetchone() == py.execute(sql, params).fetchone()
    finally:
        py.close()
        cpp.close()
