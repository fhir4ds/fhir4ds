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
    # §Age: scalar strings (certain results); partial-precision inputs
    # would surface interval JSON instead.
    expected = {
        "CalcYearsAt": ('26',),
        "CalcMonthsAt": ('313',),
        "CalcWeeksAt": ('2',),
        "CalcDaysAt": ('2',),
        "CalcLeapYearsAt": ('21',),
        "CalcLeapMonthsAt": ('12',),
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
        ("SELECT AgeInYearsAt(?, ?)", [patient, "2026-05-14"], ('26',)),
        ("SELECT AgeInMonthsAt(?, ?)", [patient, "2026-06-14"], ('313',)),
        ("SELECT AgeInWeeksAt(?, ?)", [patient, "2000-05-28"], ('2',)),
        ("SELECT AgeInDaysAt(?, ?)", [patient, "2000-05-16"], ('2',)),
        # Day-precision birthDate at hour-or-finer precision is a §Age
        # uncertainty interval (time-of-day unknown); the high bound is the
        # age assuming a midnight birth.
        ("SELECT AgeInHoursAt(?, ?)", [patient, "2000-05-14T01:00:00Z"],
         ('{"start":-22,"end":1,"lowClosed":true,"highClosed":true}',)),
        ("SELECT AgeInMinutesAt(?, ?)", [patient, "2000-05-14T00:01:00Z"],
         ('{"start":-1438,"end":1,"lowClosed":true,"highClosed":true}',)),
        ("SELECT AgeInSecondsAt(?, ?)", [patient, "2000-05-14T00:00:01Z"],
         ('{"start":-86398,"end":1,"lowClosed":true,"highClosed":true}',)),
        ("SELECT AgeInYearsAt(?, ?)", [leap_patient, "2021-02-28"], ('1',)),
        ("SELECT AgeInMonthsAt(?, ?)", [leap_patient, "2021-02-28"], ('12',)),
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2000-05-14", "2026-05-14"], ('26',)),
        ("SELECT CalculateAgeInMonthsAt(?, ?)", ["2000-05-14", "2026-06-14"], ('313',)),
        ("SELECT CalculateAgeInWeeksAt(?, ?)", ["2000-05-14", "2000-05-28"], ('2',)),
        ("SELECT CalculateAgeInDaysAt(?, ?)", ["2000-05-14", "2000-05-16"], ('2',)),
        ("SELECT CalculateAgeInHoursAt(?, ?)", ["2000-05-15T00:00:00Z", "2000-05-15T01:00:00Z"], ('1',)),
        ("SELECT CalculateAgeInMinutesAt(?, ?)", ["2000-05-15T00:00:00Z", "2000-05-15T00:01:00Z"], ('1',)),
        ("SELECT CalculateAgeInSecondsAt(?, ?)", ["2000-05-15T00:00:00Z", "2000-05-15T00:00:01Z"], ('1',)),
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2000-02-29", "2021-02-28"], ('21',)),
        ("SELECT CalculateAgeInMonthsAt(?, ?)", ["2020-02-29", "2021-02-28"], ('12',)),
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
    patient = json.dumps({"resourceType": "Patient", "birthDate": "2000-05-14"})
    leap_patient = json.dumps({"resourceType": "Patient", "birthDate": "2020-02-29"})
    cases = [
        ("SELECT AgeInYearsAt(?, ?)", [leap_patient, "2021-02-28"], ('1',)),
        ("SELECT AgeInMonthsAt(?, ?)", [leap_patient, "2021-02-28"], ('12',)),
        ("SELECT AgeInHoursAt(?, ?)", [patient, "2000-05-14T01:00:00Z"],
         ('{"start":-22,"end":1,"lowClosed":true,"highClosed":true}',)),
        ("SELECT AgeInMinutesAt(?, ?)", [patient, "2000-05-14T00:01:00Z"],
         ('{"start":-1438,"end":1,"lowClosed":true,"highClosed":true}',)),
        ("SELECT AgeInSecondsAt(?, ?)", [patient, "2000-05-14T00:00:01Z"],
         ('{"start":-86398,"end":1,"lowClosed":true,"highClosed":true}',)),
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2000-02-29", "2021-02-28"], ('21',)),
        ("SELECT CalculateAgeInMonthsAt(?, ?)", ["2020-02-29", "2021-02-28"], ('12',)),
        ("SELECT CalculateAgeInHoursAt(?, ?)", ["2000-05-15T00:00:00Z", "2000-05-15T01:00:00Z"], ('1',)),
        ("SELECT CalculateAgeInMinutesAt(?, ?)", ["2000-05-15T00:00:00Z", "2000-05-15T00:01:00Z"], ('1',)),
        ("SELECT CalculateAgeInSecondsAt(?, ?)", ["2000-05-15T00:00:00Z", "2000-05-15T00:00:01Z"], ('1',)),
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
            assert row[1] is not None  # AgeWeeks (current-date dependent)
            assert row[2] is not None  # AgeHours (§Age interval, day-precision birth)
            # AgeWeeksAt certain; hour-or-finer At on a day-precision birthDate
            # are §Age uncertainty intervals whose high bound assumes midnight.
            assert row[3] == "2"
            assert json.loads(row[4])["end"] == 1
            assert json.loads(row[5])["end"] == 1
            assert json.loads(row[6])["end"] == 1
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
            assert con.execute(sql).fetchone() == ("p1", "1", "12")
        with no_python_connection() as no_py:
            no_py.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient])
            assert no_py.execute(sql).fetchone() == ("p1", "1", "12")
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


def test_cql_string_in_codesystem_raises_unsupported_per_spec() -> None:
    """CQL 1.5.3 §In (Codesystem) String overload requires a terminology
    service to verify code membership in an externally-defined code system.
    The translator must not silently return TRUE for any non-empty string;
    it must surface the missing capability as a TranslationError.

    Null and empty-string operands still return False per the spec's
    "If the code argument is null, the result is false" rule.
    """
    from fhir4ds.cql.errors import TranslationError

    # Non-empty string: must raise.
    cql_real = """library RealCodeInCS version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
context Patient
define Probe: '8867-4' in LOINC
"""
    with __import__("pytest").raises(TranslationError):
        translate_cql(cql_real)

    # Empty string: spec-compliant False (null argument rule).
    cql_empty = """library EmptyInCS version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
context Patient
define Probe: '' in LOINC
"""
    translated_empty = translate_cql(cql_empty)
    assert translated_empty["Probe"].to_sql() == "FALSE"

    # null literal: spec-compliant False.
    cql_null = """library NullInCS version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
context Patient
define Probe: null as String in LOINC
"""
    translated_null = translate_cql(cql_null)
    assert translated_null["Probe"].to_sql() == "FALSE"


def test_cql_string_in_valueset_overload_matches_per_spec_cql21_skeptic() -> None:
    """CQL 1.5.3 §In (Valueset) String overload: "For the String overload, if
    the given valueset contains a code with an equivalent code element, the
    result is true. Note that for this overload, because the code being tested
    cannot specify code system information, if the resolved value set contains
    codes from multiple code systems, a run-time error is thrown because the
    operation is ambiguous."

    Previously the UDF returned False for any String-overload call where the
    cache had the code under a real (non-empty) system, because the source's
    synthetic resource encodes system="" and the code-only fallback only
    matched when the cache itself had ("", code) entries. The fix scans the
    cache for any entry with the matching code value: 1 distinct non-empty
    system → True; multiple distinct non-empty systems → NULL (ambiguous per
    three-valued logic); 0 → only matches if cache has empty-system entry.
    """
    vs_url = "http://example.org/fhir/ValueSet/vs21skeptic"
    vs_multi_url = "http://example.org/fhir/ValueSet/vs21multi"

    def _make_cpp_con():
        con = _cpp_connection()
        con.execute("SELECT cql_valueset_cache_clear()")
        con.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [vs_url, "http://loinc.org", "8867-4"])
        con.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [vs_multi_url, "http://loinc.org", "8867-4"])
        con.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [vs_multi_url, "http://snomed.info/sct", "8867-4"])
        return con

    def _make_py_con():
        con = _python_only_connection()
        con.remove_function("in_valueset")
        con.create_function(
            "in_valueset",
            createValuesetMembershipUdf({
                VALUESET_URL: {("http://loinc.org", "8867-4"), ("", "code-only")},
                vs_url: {("http://loinc.org", "8867-4")},
                vs_multi_url: {
                    ("http://loinc.org", "8867-4"),
                    ("http://snomed.info/sct", "8867-4"),
                },
            }),
            null_handling="special",
        )
        return con

    cql = f"""library VS21Skeptic version '1.0.0'
using FHIR version '4.0.1'
context Patient
valueset SingleVS: '{vs_url}'
valueset MultiVS: '{vs_multi_url}'
define StringInSingleVS: '8867-4' in SingleVS
define StringNotInSingleVS: '9999-9' in SingleVS
define AmbiguousStringInMultiVS: '8867-4' in MultiVS
define UnambiguousStringInMultiVS: '9999-9' in MultiVS
"""
    translated = translate_cql(cql)
    expected = {
        "StringInSingleVS": True,           # Single system containing code → True
        "StringNotInSingleVS": False,        # Code absent → False
        "AmbiguousStringInMultiVS": None,    # Multi-system ambiguity → None
        "UnambiguousStringInMultiVS": False, # Code absent → False
    }
    for con_factory in (_make_cpp_con, _make_py_con):
        con = con_factory()
        try:
            for name, want in expected.items():
                sql = f"SELECT {translated[name].to_sql()} AS v"
                got = con.execute(sql).fetchone()[0]
                assert got == want, f"{con_factory.__name__} {name}: want {want}, got {got}"
        finally:
            con.close()


def test_cql_clinical_static_list_membership_overloads_match_cpp_registration() -> None:
    cql = """library ClinicalListTerminologyOps version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
codesystem SNOMED: 'http://snomed.info/sct'
valueset Vitals: 'http://example.org/fhir/ValueSet/vitals'
code HR: '8867-4' from LOINC display 'Heart rate'
code Other: '123' from SNOMED
code HRNoDisplay: '8867-4' from LOINC
concept BP: { Other, HRNoDisplay } display 'BP'
concept OtherConcept: { Other } display 'Other'
context Patient
define CodeListInCodeSystem: { Other, HR } in LOINC
define CodeListNotInCodeSystem: { Other } in LOINC
define ConceptListInCodeSystem: { OtherConcept, BP } in LOINC
define CodeListInValueSet: { Other, HR } in Vitals
define CodeListNotInValueSet: { Other } in Vitals
define StringListInValueSet: { 'not-here', 'code-only' } in Vitals
define StringListNotInValueSet: { 'not-here' } in Vitals
define ConceptListInValueSet: { OtherConcept, BP } in Vitals
"""
    translated = translate_cql(cql)
    expected = {
        "CodeListInCodeSystem": True,
        "CodeListNotInCodeSystem": False,
        "ConceptListInCodeSystem": True,
        "CodeListInValueSet": True,
        "CodeListNotInValueSet": False,
        "StringListInValueSet": True,
        "StringListNotInValueSet": False,
        "ConceptListInValueSet": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for name, expected_value in expected.items():
                assert con.execute(f"SELECT {translated[name].to_sql()}").fetchone() == (
                    expected_value,
                ), name
        with no_python_connection() as no_py:
            _load_valueset_table(no_py)
            no_py.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [VALUESET_URL, "http://loinc.org", "8867-4"])
            no_py.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [VALUESET_URL, "", "code-only"])
            for name, expected_value in expected.items():
                assert no_py.execute(f"SELECT {translated[name].to_sql()}").fetchone() == (
                    expected_value,
                ), name
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_expand_valueset_direct_surface_matches_no_python_registration() -> None:
    valueset_arg = json.dumps(
        {"resourceType": "ValueSet", "id": VALUESET_URL, "name": "Vitals"}
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            assert con.execute(
                "SELECT array_length(ExpandValueSet(?))", [valueset_arg]
            ).fetchone() == (2,)
            assert con.execute("SELECT ExpandValueSet(NULL)").fetchone() == (None,)
        with no_python_connection() as no_py:
            _load_valueset_table(no_py)
            assert no_py.execute(
                "SELECT array_length(ExpandValueSet(?))", [valueset_arg]
            ).fetchone() == (2,)
            assert no_py.execute("SELECT ExpandValueSet(NULL)").fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_versioned_expand_valueset_matches_membership_url() -> None:
    valueset_version = "2026"
    versioned_url = f"{VALUESET_URL}|{valueset_version}"
    cql = f"""library VersionedClinicalTerminologyOps version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
valueset Vitals: '{VALUESET_URL}' version '{valueset_version}'
code HR: '8867-4' from LOINC display 'Heart rate'
context Patient
define VersionedExpandedCount: Count(ExpandValueSet(Vitals))
define VersionedMembership: HR in Vitals
"""
    translated = translate_cql(cql)
    valueset_arg = json.dumps(
        {
            "resourceType": "ValueSet",
            "id": VALUESET_URL,
            "version": valueset_version,
            "name": "Vitals",
        }
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        py.remove_function("in_valueset")
        py.create_function(
            "in_valueset",
            createValuesetMembershipUdf(
                {
                    VALUESET_URL: {("http://loinc.org", "8867-4"), ("", "code-only")},
                    versioned_url: {("http://loinc.org", "8867-4")},
                }
            ),
            null_handling="special",
        )
        for con in (py, cpp):
            con.execute("INSERT INTO valueset_codes VALUES (?, ?, ?, ?)", [versioned_url, "http://loinc.org", "8867-4", "Heart rate"])
            if con is cpp:
                con.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [versioned_url, "http://loinc.org", "8867-4"])
            assert con.execute(
                "SELECT array_length(ExpandValueSet(?))", [valueset_arg]
            ).fetchone() == (1,)
            assert con.execute(
                f"SELECT {translated['VersionedExpandedCount'].to_sql()}"
            ).fetchone() == (1,)
            assert con.execute(
                f"SELECT {translated['VersionedMembership'].to_sql()}"
            ).fetchone() == (True,)
        with no_python_connection() as no_py:
            no_py.execute("INSERT INTO valueset_codes VALUES (?, ?, ?, ?)", [versioned_url, "http://loinc.org", "8867-4", "Heart rate"])
            no_py.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [versioned_url, "http://loinc.org", "8867-4"])
            assert no_py.execute(
                "SELECT array_length(ExpandValueSet(?))", [valueset_arg]
            ).fetchone() == (1,)
            assert no_py.execute(
                f"SELECT {translated['VersionedExpandedCount'].to_sql()}"
            ).fetchone() == (1,)
            assert no_py.execute(
                f"SELECT {translated['VersionedMembership'].to_sql()}"
            ).fetchone() == (True,)
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_null_terminology_membership_is_false() -> None:
    cql = """library ClinicalNullTerminologyOps version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
valueset Vitals: 'http://example.org/fhir/ValueSet/vitals'
context Patient
define NullCodeInCodeSystem: null as Code in LOINC
define NullStringInCodeSystem: null as String in LOINC
define NullConceptInCodeSystem: null as Concept in LOINC
define NullCodeInValueSet: null as Code in Vitals
define NullStringInValueSet: null as String in Vitals
define NullConceptInValueSet: null as Concept in Vitals
"""
    translated = translate_cql(cql)
    expected = {
        "NullCodeInCodeSystem": False,
        "NullStringInCodeSystem": False,
        "NullConceptInCodeSystem": False,
        "NullCodeInValueSet": False,
        "NullStringInValueSet": False,
        "NullConceptInValueSet": False,
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


def test_cql_concept_in_valueset_with_literal_codes_matches_per_spec_cql21_historian() -> None:
    """CQL 1.5.3 Appendix B In (ValueSet): "If the first argument is a
    Concept, returns true if any code in the concept is in the valueset."

    CQL-21 HISTORIAN iteration 1 found that the prior translator only
    extracted Literal field values from InstanceExpression, so a Concept
    with a codes ListExpression field (the natural parse of
    `Concept { codes: { Code { ... } } }`) was not recognized at
    translation time. The translator fell through to generic JSON
    translation producing a non-FHIR {codes:[...]} shape that the
    in_valueset UDF cannot navigate, so Concept-in-ValueSet always
    returned False even when the cache held a matching code.

    The fix recurses into each Code InstanceExpression in the
    ListExpression and emits a proper FHIR-shaped synthetic resource
    per code, OR-chaining the results.
    """
    cql = """library ConceptInValueSetCql21Historian version '1.0.0'
using FHIR version '4.0.1'
valueset Vitals: 'http://example.org/fhir/ValueSet/vitals'
context Patient

// Single-code Concept with a matching cache entry -> True
define ConceptSingleMatch:
  Concept { codes: { Code { code: '8867-4', system: 'http://loinc.org' } } }
    in Vitals

// Multi-code Concept where any code matches -> True (OR-chain)
define ConceptMultiAnyMatch:
  Concept {
    codes: {
      Code { code: '8867-4', system: 'http://loinc.org' },
      Code { code: '12345', system: 'http://snomed.info/sct' }
    }
  } in Vitals

// Multi-code Concept where no code matches -> False
define ConceptMultiNoMatch:
  Concept {
    codes: {
      Code { code: '9999-9', system: 'http://loinc.org' },
      Code { code: '8888-8', system: 'http://snomed.info/sct' }
    }
  } in Vitals

// Single-code Concept with no match -> False
define ConceptSingleNoMatch:
  Concept { codes: { Code { code: '9999-9', system: 'http://loinc.org' } } }
    in Vitals
"""
    translated = translate_cql(cql)
    expected = {
        "ConceptSingleMatch": True,
        "ConceptMultiAnyMatch": True,
        "ConceptMultiNoMatch": False,
        "ConceptSingleNoMatch": False,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            py_row = py.execute(sql).fetchone()
            cpp_row = cpp.execute(sql).fetchone()
            assert py_row == (expected_value,), f"{name}: py={py_row!r}"
            assert cpp_row == (expected_value,), f"{name}: cpp={cpp_row!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_age_partial_birthdate_uncertainty_matches_cpp_registration() -> None:
    """CQL-21 QA-001 regression: §Age/§CalculateAgeAt partial birthDates.

    CQL 1.5 Appendix B: age operators are duration calculations; when the
    birthDate precision is below the operator precision the result is an
    uncertainty over the range of possible values (closed interval JSON),
    on both the Python fallback and the native C++ extension.
    """
    interval = '{"start":%d,"end":%d,"lowClosed":true,"highClosed":true}'
    cases = [
        # (sql, params, expected)
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2012", "2026-05-14"], interval % (13, 14)),
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2012-06", "2026-05-14"], "13"),
        ("SELECT CalculateAgeInMonthsAt(?, ?)", ["2012-06", "2026-05-14"], interval % (166, 167)),
        ("SELECT CalculateAgeInDaysAt(?, ?)", ["2012", "2012-02-28"], interval % (-307, 58)),
        ("SELECT CalculateAgeInYearsAt(?, ?)", ["2000-05-14", "2026-05-14"], "26"),
        ("SELECT cqlUncertainCompare(CalculateAgeInYearsAt(?, ?), '13', '>=')",
         ["2012", "2026-05-14"], True),
        ("SELECT cqlUncertainCompare(CalculateAgeInYearsAt(?, ?), '14', '>=')",
         ["2012", "2026-05-14"], None),
        ("SELECT cqlUncertainCompare(CalculateAgeInYearsAt(?, ?), '15', '>=')",
         ["2012", "2026-05-14"], False),
        # Uncertain [18, 19] vs an adult threshold: true only when certain.
        ("SELECT cqlUncertainCompare(CalculateAgeInYearsAt(?, ?), '18', '>=')",
         ["2007", "2026-05-14"], True),
        ("SELECT cqlUncertainCompare(CalculateAgeInYearsAt(?, ?), '19', '>=')",
         ["2007", "2026-05-14"], None),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    for sql, params, expected in cases:
        py_row = py.execute(sql, params).fetchone()
        cpp_row = cpp.execute(sql, params).fetchone()
        assert py_row == (expected,), f"py {sql}: {py_row!r} != {(expected,)!r}"
        assert cpp_row == (expected,), f"cpp {sql}: {cpp_row!r} != {(expected,)!r}"
    # Patient-context population SQL: year-precision FHIR birthDate '1990'
    # at @2026-05-14 must surface the [35, 36] uncertainty interval. The
    # boolean define B is filter-based in population mode (uncertain NULL
    # excludes the row -> False at the define boundary), so the scalar
    # NULL-vs-false distinction is asserted above via cqlUncertainCompare.
    cql = """library PartialAge version '1.0.0'
using FHIR version '4.0.1'
context Patient
define A: AgeInYearsAt(@2026-05-14)
define B: AgeInYearsAt(@2026-05-14) >= 36
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={"A": "A", "B": "B"},
    )
    patient = json.dumps({"resourceType": "Patient", "id": "p1", "birthDate": "1990"})
    for con in (py, cpp):
        con.execute(
            "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
        )
        con.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient])
        row = con.execute(sql).fetchone()
        assert row[1] == interval % (35, 36), row
        assert row[2] is False, row
    py.close()
    cpp.close()


def test_cql_clinical_age_in_list_negate_minmax_uncertainty_matches_cpp_registration() -> None:
    """CQL-21 HISTORIAN QA-001..003 regression.

    Post-uncertainty-fix age operands are §22.21 VARCHAR; generic
    lowerings must stay uncertainty-aware: In (list) equality,
    unary negation (-x ≡ x * -1), and scalar/list Min/Max.
    """
    crisp = {"resourceType": "Patient", "id": "p1", "birthDate": "1990-05-14"}
    partial = {"resourceType": "Patient", "id": "p2", "birthDate": "1990"}
    cases = [
        # (expression, patient_id, expected)
        ("AgeInYearsAt(@2026-05-14) in { 9, 36 }", "p1", True),
        ("AgeInYearsAt(@2026-05-14) in { 9, 40 }", "p1", False),
        # Uncertain [35,36] vs 36: could be 35 or 36 -> population filter
        # excludes the row (NULL -> False at the define boundary).
        ("AgeInYearsAt(@2026-05-14) in { 9, 36 }", "p2", False),
        ("- AgeInYearsAt(@2026-05-14)", "p1", "-36"),
        ("- AgeInYearsAt(@2026-05-14)", "p2",
         '{"start":-36,"end":-35,"lowClosed":true,"highClosed":true}'),
        ("Max(AgeInYearsAt(@2026-05-14), 30)", "p1", "36"),
        ("Min(AgeInYearsAt(@2026-05-14), 30)", "p1", "30"),
        ("Min({ AgeInYearsAt(@2026-05-14), AgeInYearsAt(@2017-05-14) })", "p1", "27"),
        ("Max({ AgeInYearsAt(@2026-05-14), AgeInYearsAt(@2017-05-14) })", "p1", "36"),
        ("Min({ AgeInYearsAt(@2026-05-14), AgeInYearsAt(@2017-05-14) })", "p2",
         '{"start":26,"end":27,"lowClosed":true,"highClosed":true}'),
    ]
    sql_by_case = []
    for expression, _pid, _expected in cases:
        cql = (
            "library L\nusing FHIR version '4.0.1'\ncontext Patient\n"
            f"define X: {expression}"
        )
        sql_by_case.append(
            CQLToSQLTranslator().translate_library_to_population_sql(
                parse_cql(cql), output_columns={"X": "X"}
            )
        )
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            for pid, source in (("p1", crisp), ("p2", partial)):
                con.execute(
                    "INSERT INTO resources VALUES (?, 'Patient', ?::JSON, ?)",
                    [pid, json.dumps(source), pid],
                )
            for (expression, pid, expected), sql in zip(cases, sql_by_case):
                rows = {r[0]: r[-1] for r in con.execute(sql).fetchall()}
                got = rows.get(pid)
                assert got == expected, f"{expression} [{pid}]: {got!r} != {expected!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_explorer_dynamic_code_equal_and_aggregates_regression() -> None:
    """CQL-21 EXPLORER QA-001..003 regression.

    QA-001: `=` between a dynamically retrieved code and a literal Code is
    an exact match on code/system/version/display (Authors Guide); the old
    raw CodeableConcept-JSON vs Code-JSON lowering could never match.
    QA-002: Sum over a literal list with §22.21 uncertainty elements must
    propagate ([Σ lows, Σ highs]), never silently drop intervals; Avg/Median
    over uncertain elements surface null rather than a wrong crisp value.
    QA-003: `Average` must resolve to the avg aggregate lowering, not leak
    an unregistered `Average(...)` SQL call.
    """
    observation = json.dumps(
        {
            "resourceType": "Observation",
            "id": "o1",
            "subject": {"reference": "Patient/p1"},
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4",
                                 "display": "Heart rate"}]},
        }
    )
    cases = [
        # QA-001: exact-match Equal on retrieved coding (all components match)
        ("First([Observation] O return O.code) = HR", "p1", True),
        # display differs (coding has no display) -> not an exact match
        ("First([Observation] O return O.code) = HRNoDisplay", "p1", False),
        ("First([Observation] O return O.code) != HR", "p1", False),
        # QA-002: uncertainty propagates through Sum (26 + [35,36] -> [61,62])
        ("Sum({ AgeInYearsAt(@2026-06-01), CalculateAgeInYears(@2000-01-01) })",
         "p2", '{"start":61,"end":62,"lowClosed":true,"highClosed":true}'),
        # crisp-only lists keep the exact typed sum
        ("Sum({ CalculateAgeInYears(@2000-01-01), CalculateAgeInYears(@1994-06-01) })",
         "p2", "58"),
        # Avg/Median over an uncertain element cannot be represented -> null
        ("Median({ AgeInYearsAt(@2026-06-01), CalculateAgeInYears(@2000-01-01) })",
         "p2", None),
        # QA-003: Average lowers to a registered aggregate (exact Decimal)
        ("Average({ 1, 2, 3 })", "p2", "2.00000000"),
    ]
    sql_by_case = []
    for expression, _pid, _expected in cases:
        cql = (
            "library L\nusing FHIR version '4.0.1'\n"
            "codesystem LOINC: 'http://loinc.org'\n"
            "code HR: '8867-4' from LOINC display 'Heart rate'\n"
            "code HRNoDisplay: '8867-4' from LOINC\n"
            "context Patient\n"
            f"define X: {expression}"
        )
        sql_by_case.append(
            CQLToSQLTranslator().translate_library_to_population_sql(
                parse_cql(cql), output_columns={"X": "X"}
            )
        )
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute(
                "INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')",
                [json.dumps({"resourceType": "Patient", "id": "p1",
                             "birthDate": "1990-05-14"})],
            )
            con.execute(
                "INSERT INTO resources VALUES ('p2', 'Patient', ?::JSON, 'p2')",
                [json.dumps({"resourceType": "Patient", "id": "p2",
                             "birthDate": "1990"})],
            )
            con.execute(
                "INSERT INTO resources VALUES ('o1', 'Observation', ?::JSON, 'p1')",
                [observation],
            )
            for (expression, pid, expected), sql in zip(cases, sql_by_case):
                rows = {r[0]: r[-1] for r in con.execute(sql).fetchall()}
                got = rows.get(pid)
                if expected is not None and isinstance(got, str) and expected != "None":
                    got = str(got)
                assert got == expected or str(got) == expected, (
                    f"{expression} [{pid}]: {got!r} != {expected!r}"
                )
    finally:
        py.close()
        cpp.close()
