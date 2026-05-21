"""CQL clinical operator parity checks."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import FunctionRef
from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql
from .wasm_runtime_helpers import no_python_connection


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
    _load_valueset_table(con)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    con.execute("SELECT cql_valueset_cache_clear()")
    con.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [VALUESET_URL, "http://loinc.org", "8867-4"])
    con.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [VALUESET_URL, "", "code-only"])
    _load_valueset_table(con)
    return con


def _load_valueset_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS valueset_codes (
            valueset_url VARCHAR,
            system VARCHAR,
            code VARCHAR,
            display VARCHAR
        )
        """
    )
    con.execute("DELETE FROM valueset_codes WHERE valueset_url = ?", [VALUESET_URL])
    con.execute(
        "INSERT INTO valueset_codes VALUES (?, ?, ?, ?)",
        [VALUESET_URL, "http://loinc.org", "8867-4", "Heart rate"],
    )
    con.execute(
        "INSERT INTO valueset_codes VALUES (?, ?, ?, ?)",
        [VALUESET_URL, "", "code-only", None],
    )


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
        "CalcLeapYearsAt": (21,),
        "CalcLeapMonthsAt": (12,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            assert py.execute(sql).fetchone() == expected[name], name
            assert cpp.execute(sql).fetchone() == expected[name], name
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                assert no_py.execute(f"SELECT {expr.to_sql()}").fetchone() == expected[name], name
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
    leap_patient = json.dumps({"resourceType": "Patient", "birthDate": "2020-02-29"})
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
        ("SELECT AgeInHoursAt(?, ?)", [patient, "2000-05-14T01:00:00Z"], (1,)),
        ("SELECT AgeInMinutesAt(?, ?)", [patient, "2000-05-14T00:01:00Z"], (1,)),
        ("SELECT AgeInSecondsAt(?, ?)", [patient, "2000-05-14T00:00:01Z"], (1,)),
        ("SELECT AgeInYearsAt(?, ?)", [leap_patient, "2021-02-28"], (1,)),
        ("SELECT AgeInMonthsAt(?, ?)", [leap_patient, "2021-02-28"], (12,)),
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2000-05-14", "2026-05-14"], (26,)),
        ("SELECT CalculateAgeInMonthsAt(?, ?)", ["2000-05-14", "2026-06-14"], (313,)),
        ("SELECT CalculateAgeInWeeksAt(?, ?)", ["2000-05-14", "2000-05-28"], (2,)),
        ("SELECT CalculateAgeInDaysAt(?, ?)", ["2000-05-14", "2000-05-16"], (2,)),
        ("SELECT CalculateAgeInHoursAt(?, ?)", ["2000-05-15T00:00:00Z", "2000-05-15T01:00:00Z"], (1,)),
        ("SELECT CalculateAgeInMinutesAt(?, ?)", ["2000-05-15T00:00:00Z", "2000-05-15T00:01:00Z"], (1,)),
        ("SELECT CalculateAgeInSecondsAt(?, ?)", ["2000-05-15T00:00:00Z", "2000-05-15T00:00:01Z"], (1,)),
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2000-02-29", "2021-02-28"], (21,)),
        ("SELECT CalculateAgeInMonthsAt(?, ?)", ["2020-02-29", "2021-02-28"], (12,)),
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


def test_cql_clinical_age_direct_surface_matches_no_python_registration() -> None:
    leap_patient = json.dumps({"resourceType": "Patient", "birthDate": "2020-02-29"})
    cases = [
        ("SELECT AgeInYearsAt(?, ?)", [leap_patient, "2021-02-28"], (1,)),
        ("SELECT AgeInMonthsAt(?, ?)", [leap_patient, "2021-02-28"], (12,)),
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2000-02-29", "2021-02-28"], (21,)),
        ("SELECT CalculateAgeInMonthsAt(?, ?)", ["2020-02-29", "2021-02-28"], (12,)),
    ]

    with no_python_connection() as con:
        for sql, params, expected in cases:
            assert con.execute(sql, params).fetchone() == expected


def _cql_clinical_library() -> str:
    return """library ClinicalOps version '1.0.0'
using FHIR version '4.0.1'
context Patient
define CalcYearsAt: CalculateAgeInYearsAt(@2000-05-14, @2026-05-14)
define CalcMonthsAt: CalculateAgeInMonthsAt(@2000-05-14, @2026-06-14)
define CalcWeeksAt: CalculateAgeInWeeksAt(@2000-05-14, @2000-05-28)
define CalcDaysAt: CalculateAgeInDaysAt(@2000-05-14, @2000-05-16)
define CalcLeapYearsAt: CalculateAgeInYearsAt(@2000-02-29, @2021-02-28)
define CalcLeapMonthsAt: CalculateAgeInMonthsAt(@2020-02-29, @2021-02-28)
"""


def test_cql_clinical_age_patient_context_all_precisions_execute() -> None:
    cql = """library ClinicalAgeContext version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AgeWeeks: AgeInWeeks()
define AgeHours: AgeInHours()
define AgeWeeksAt: AgeInWeeksAt(@2000-05-28)
define AgeHoursAt: AgeInHoursAt(@2000-05-14T01:00:00Z)
define AgeMinutesAt: AgeInMinutesAt(@2000-05-14T00:01:00Z)
define AgeSecondsAt: AgeInSecondsAt(@2000-05-14T00:00:01Z)
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "AgeWeeks": "AgeWeeks",
            "AgeHours": "AgeHours",
            "AgeWeeksAt": "AgeWeeksAt",
            "AgeHoursAt": "AgeHoursAt",
            "AgeMinutesAt": "AgeMinutesAt",
            "AgeSecondsAt": "AgeSecondsAt",
        },
    )

    patient = json.dumps({"resourceType": "Patient", "id": "p1", "birthDate": "2000-05-14"})
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient])
            row = con.execute(sql).fetchone()
            assert row[0] == "p1"
            assert row[1] is not None
            assert row[2] is not None
            assert row[3:] == (2, 1, 1, 1)
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_age_patient_context_leap_day_anniversary_execute() -> None:
    cql = """library ClinicalAgeLeapContext version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AgeYearsAt: AgeInYearsAt(@2021-02-28)
define AgeMonthsAt: AgeInMonthsAt(@2021-02-28)
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "AgeYearsAt": "AgeYearsAt",
            "AgeMonthsAt": "AgeMonthsAt",
        },
    )

    patient = json.dumps({"resourceType": "Patient", "id": "p1", "birthDate": "2020-02-29"})
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient])
            assert con.execute(sql).fetchone() == ("p1", 1, 12)
        with no_python_connection() as no_py:
            no_py.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient])
            assert no_py.execute(sql).fetchone() == ("p1", 1, 12)
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_static_terminology_operators_match_cpp_registration() -> None:
    cql = """library ClinicalTerminologyOps version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
valueset Vitals: 'http://example.org/fhir/ValueSet/vitals'
code HR: '8867-4' from LOINC display 'Heart rate'
code HRNoDisplay: '8867-4' from LOINC
code DIA: '8462-4' from LOINC
concept BP: { HR, DIA } display 'BP'
concept HRConcept: { HRNoDisplay } display 'HR'
context Patient
define CodeInCodeSystem: HR in LOINC
define ConceptInCodeSystem: BP in LOINC
define StringInCodeSystem: '8867-4' in LOINC
define CodeInValueSet: HR in Vitals
define ConceptInValueSet: BP in Vitals
define StringInValueSet: 'code-only' in Vitals
define ExpandedCount: Count(ExpandValueSet(Vitals))
define CodeEqualDifferentComponents: HRNoDisplay = HR
define CodeEquivalentIgnoresDisplay: HRNoDisplay ~ HR
define ConceptEquivalentIntersection: BP ~ HRConcept
"""
    translated = translate_cql(cql)
    expected = {
        "CodeInCodeSystem": True,
        "ConceptInCodeSystem": True,
        "StringInCodeSystem": True,
        "CodeInValueSet": True,
        "ConceptInValueSet": True,
        "StringInValueSet": True,
        "ExpandedCount": 2,
        "CodeEqualDifferentComponents": None,
        "CodeEquivalentIgnoresDisplay": True,
        "ConceptEquivalentIntersection": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), name
            assert cpp.execute(sql).fetchone() == (expected_value,), name
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_dynamic_codesystem_membership_matches_cpp_registration() -> None:
    cql = """library DynamicClinicalTerminologyOps version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
context Patient
define DynamicCodeInCodeSystem:
  exists ([Observation] O where O.code in LOINC)
define DynamicConceptInCodeSystem:
  exists ([Observation] O where O.code as Concept in LOINC)
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "DynamicCodeInCodeSystem": "DynamicCodeInCodeSystem",
            "DynamicConceptInCodeSystem": "DynamicConceptInCodeSystem",
        },
    )

    patient_1 = json.dumps({"resourceType": "Patient", "id": "p1"})
    patient_2 = json.dumps({"resourceType": "Patient", "id": "p2"})
    loinc_observation = json.dumps(
        {
            "resourceType": "Observation",
            "id": "o1",
            "subject": {"reference": "Patient/p1"},
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
        }
    )
    snomed_observation = json.dumps(
        {
            "resourceType": "Observation",
            "id": "o2",
            "subject": {"reference": "Patient/p2"},
            "code": {"coding": [{"system": "http://snomed.info/sct", "code": "123"}]},
        }
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient_1])
            con.execute("INSERT INTO resources VALUES ('p2', 'Patient', ?::JSON, 'p2')", [patient_2])
            con.execute("INSERT INTO resources VALUES ('o1', 'Observation', ?::JSON, 'p1')", [loinc_observation])
            con.execute("INSERT INTO resources VALUES ('o2', 'Observation', ?::JSON, 'p2')", [snomed_observation])
            assert con.execute(sql).fetchall() == [
                ("p1", True, True),
                ("p2", False, False),
            ]
    finally:
        py.close()
        cpp.close()
