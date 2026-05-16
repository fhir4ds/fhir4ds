"""CQL clinical operator parity checks."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import FunctionRef
from fhir4ds.cql.translator import translate_cql


VALUESET_URL = "http://example.org/fhir/ValueSet/vitals"


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    con.remove_function("in_valueset")
    con.create_function(
        "in_valueset",
        createValuesetMembershipUdf({VALUESET_URL: {("http://loinc.org", "8867-4"), ("", "code-only")}}),
        null_handling="special",
    )
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    con.execute("SELECT cql_valueset_cache_clear()")
    con.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [VALUESET_URL, "http://loinc.org", "8867-4"])
    con.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [VALUESET_URL, "", "code-only"])
    return con


def test_cql_clinical_expressions_parse_and_translate() -> None:
    for expression in [
        "CalculateAgeInYearsAt(@2000-05-14, @2026-05-14)",
        "CalculateAgeInMonthsAt(@2000-05-14, @2026-06-14)",
        "CalculateAgeInWeeksAt(@2000-05-14, @2000-05-28)",
        "CalculateAgeInDaysAt(@2000-05-14, @2000-05-16)",
    ]:
        assert isinstance(parse_expression(expression), FunctionRef)

    translated = translate_cql(_cql_clinical_library())
    assert "CalculateAgeInYearsAt" in str(translated["CalcYearsAt"])
    assert "CalculateAgeInMonthsAt" in str(translated["CalcMonthsAt"])
    assert "CalculateAgeInWeeksAt" in str(translated["CalcWeeksAt"])
    assert "CalculateAgeInDaysAt" in str(translated["CalcDaysAt"])


def test_cql_clinical_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_clinical_library())
    expected = {
        "CalcYearsAt": (26,),
        "CalcMonthsAt": (313,),
        "CalcWeeksAt": (2,),
        "CalcDaysAt": (2,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            assert py.execute(sql).fetchone() == expected[name], name
            assert cpp.execute(sql).fetchone() == expected[name], name
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_direct_surface_matches_cpp_registration() -> None:
    patient = json.dumps({"resourceType": "Patient", "birthDate": "2000-05-14"})
    observation = json.dumps(
        {
            "resourceType": "Observation",
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
        }
    )
    code_only = json.dumps(
        {
            "resourceType": "Observation",
            "code": {"coding": [{"code": "code-only"}]},
        }
    )

    cases = [
        ("SELECT AgeInYearsAt(?, ?)", [patient, "2026-05-14"], (26,)),
        ("SELECT AgeInMonthsAt(?, ?)", [patient, "2026-06-14"], (313,)),
        ("SELECT AgeInWeeksAt(?, ?)", [patient, "2000-05-28"], (2,)),
        ("SELECT AgeInDaysAt(?, ?)", [patient, "2000-05-16"], (2,)),
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2000-05-14", "2026-05-14"], (26,)),
        ("SELECT CalculateAgeInMonthsAt(?, ?)", ["2000-05-14", "2026-06-14"], (313,)),
        ("SELECT CalculateAgeInWeeksAt(?, ?)", ["2000-05-14", "2000-05-28"], (2,)),
        ("SELECT CalculateAgeInDaysAt(?, ?)", ["2000-05-14", "2000-05-16"], (2,)),
        ("SELECT extractFirstCode(?, 'code')", [observation], ("http://loinc.org|8867-4",)),
        ("SELECT extractFirstCodeValue(?, 'code')", [observation], ("8867-4",)),
        ("SELECT in_valueset(?, 'code', ?)", [observation, VALUESET_URL], (True,)),
        ("SELECT in_valueset(?, 'code', ?)", [code_only, VALUESET_URL], (True,)),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, params, expected in cases:
            assert py.execute(sql, params).fetchone() == expected
            assert cpp.execute(sql, params).fetchone() == expected
    finally:
        py.close()
        cpp.close()


def _cql_clinical_library() -> str:
    return """library ClinicalOps version '1.0.0'
using FHIR version '4.0.1'
context Patient
define CalcYearsAt: CalculateAgeInYearsAt(@2000-05-14, @2026-05-14)
define CalcMonthsAt: CalculateAgeInMonthsAt(@2000-05-14, @2026-06-14)
define CalcWeeksAt: CalculateAgeInWeeksAt(@2000-05-14, @2000-05-28)
define CalcDaysAt: CalculateAgeInDaysAt(@2000-05-14, @2000-05-16)
"""
