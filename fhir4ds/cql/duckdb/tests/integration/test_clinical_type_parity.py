"""CQL clinical type translation and DuckDB backend parity checks."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.context import SQLTranslationContext
from fhir4ds.cql.translator.fluent_functions import FluentFunctionTranslator
from fhir4ds.cql.translator.types import SQLIdentifier, SQLLiteral
from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql


CLINICAL_TYPES_CQL = """library ClinicalTypes version '1.0.0'
using FHIR version '4.0.1'
valueset "Example VS": 'http://example.org/fhir/ValueSet/example'
codesystem LOINC: 'http://loinc.org'
code "Systolic": '8480-6' from LOINC display 'Systolic blood pressure'
code "Diastolic": '8462-4' from LOINC display 'Diastolic blood pressure'
concept "Blood Pressure": { "Systolic" } display 'Blood pressure'
concept "Diastolic Pressure": { "Diastolic" } display 'Diastolic blood pressure'
context Patient

define ValueSetIsVocabulary: System.ValueSet{id: '123'} is Vocabulary
define CodeSystemIsVocabulary: System.CodeSystem{id: 'loinc'} is Vocabulary
define CodeIsCode: Code { code: '8480-6' } is Code
define CodeIsConcept: Code { code: '8480-6' } is Concept
define CodeSelectorIsCode: Code '8480-6' from LOINC is Code
define NamedCodeIsCode: "Systolic" is Code
define NamedConceptIsConcept: "Blood Pressure" is Concept
define NamedValueSetIsVocabulary: "Example VS" is Vocabulary
define ValueSetAsVocabulary: System.ValueSet{id: '123'} as Vocabulary
define CodeSystemAsVocabulary: System.CodeSystem{id: 'loinc'} as Vocabulary
define ValueSetAsCodeSystem: System.ValueSet{id: '123'} as CodeSystem
define CodeAsConcept: Code { code: '8480-6' } as Concept
define CodeAsVocabulary: Code { code: '8480-6' } as Vocabulary
define CodeSelectorAsConcept: Code '8480-6' from LOINC as Concept
define NamedCodeAsVocabulary: "Systolic" as Vocabulary
define NamedConceptAsVocabulary: "Blood Pressure" as Vocabulary
define ToConceptSelector: ToConcept(Code '8480-6' from LOINC)
define ToConceptNamedCode: ToConcept("Systolic")
define NamedConceptAsConcept: "Blood Pressure" as Concept
define CodeEquivalentToContainingConcept: "Systolic" ~ "Blood Pressure"
define ConceptEquivalentToContainingCode: "Blood Pressure" ~ "Systolic"
define DisjointConceptEquivalent: "Blood Pressure" ~ "Diastolic Pressure"
"""


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=False)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=False)
    return con


def _python_valueset_connection() -> duckdb.DuckDBPyConnection:
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


def _cpp_valueset_connection() -> duckdb.DuckDBPyConnection:
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
    assert json.loads(translated["Code Literal"].value) == {
        "code": "8867-4",
        "system": "http://loinc.org",
        "version": "2.74",
        "display": "Heart rate",
    }


def test_cql_clinical_type_translation_is_spec_strict() -> None:
    translated = translate_cql(CLINICAL_TYPES_CQL)

    assert translated["ValueSetIsVocabulary"].to_sql() == "TRUE"
    assert translated["CodeSystemIsVocabulary"].to_sql() == "TRUE"
    assert translated["CodeIsCode"].to_sql() == "TRUE"
    assert translated["CodeIsConcept"].to_sql() == "FALSE"
    assert translated["CodeSelectorIsCode"].to_sql() == "TRUE"
    assert translated["NamedCodeIsCode"].to_sql() == "TRUE"
    assert translated["NamedConceptIsConcept"].to_sql() == "TRUE"
    assert translated["NamedValueSetIsVocabulary"].to_sql() == "TRUE"
    assert translated["ValueSetAsCodeSystem"].to_sql() == "NULL"
    assert translated["CodeAsConcept"].to_sql() == "NULL"
    assert translated["CodeAsVocabulary"].to_sql() == "NULL"
    assert translated["CodeSelectorAsConcept"].to_sql() == "NULL"
    assert translated["NamedCodeAsVocabulary"].to_sql() == "NULL"
    assert translated["NamedConceptAsVocabulary"].to_sql() == "NULL"
    assert translated["CodeEquivalentToContainingConcept"].to_sql() == "TRUE"
    assert translated["ConceptEquivalentToContainingCode"].to_sql() == "TRUE"
    assert translated["DisjointConceptEquivalent"].to_sql() == "FALSE"


def test_cql_dynamic_fhir_clinical_assertion_uses_runtime_value() -> None:
    cql = """library ClinicalDynamic version '1.0.0'
using FHIR version '4.0.1'
codesystem SNOMEDCT: 'http://snomed.info/sct'
code "Stage": '1228889001' from SNOMEDCT display 'Stage'
context Patient

define DynamicFHIRConceptComparison:
  exists ([Observation] O where O.value as Concept ~ "Stage")
"""
    translated = translate_cql(cql)
    sql = translated["DynamicFHIRConceptComparison"].to_sql()

    assert "coding_matches" in sql
    assert "'valueCodeableConcept'" in sql
    assert "'http://snomed.info/sct'" in sql
    assert "'1228889001'" in sql
    assert "FALSE OR FALSE" not in sql
    assert "code.coding.exists()" not in sql


def test_cql_clinical_type_metadata_propagates_through_query_return() -> None:
    cql = """library ClinicalQueryTypes version '1.0.0'
using FHIR version '4.0.1'
valueset "Example VS": 'http://example.org/fhir/ValueSet/example'
codesystem LOINC: 'http://loinc.org'
code "Systolic": '8480-6' from LOINC display 'Systolic blood pressure'
concept "Blood Pressure": { "Systolic" } display 'Blood pressure'
context Patient

define QueryReturnsConceptIsConcept:
  singleton from ([Observation] O let C: "Blood Pressure" return C) is Concept
define QueryReturnsValueSetIsVocabulary:
  singleton from ([Observation] O let VS: "Example VS" return VS) is Vocabulary
"""
    translated = translate_cql(cql)

    assert translated["QueryReturnsConceptIsConcept"].to_sql() == "TRUE"
    assert translated["QueryReturnsValueSetIsVocabulary"].to_sql() == "TRUE"

    population_sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "QueryReturnsConceptIsConcept": "QueryReturnsConceptIsConcept",
            "QueryReturnsValueSetIsVocabulary": "QueryReturnsValueSetIsVocabulary",
        },
    )
    patient = json.dumps({"resourceType": "Patient", "id": "p1"})
    observation = json.dumps(
        {
            "resourceType": "Observation",
            "id": "o1",
            "subject": {"reference": "Patient/p1"},
            "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6"}]},
        }
    )

    py = _python_valueset_connection()
    cpp = _cpp_valueset_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient])
            con.execute("INSERT INTO resources VALUES ('o1', 'Observation', ?::JSON, 'p1')", [observation])
            assert con.execute(population_sql).fetchone() == ("p1", True, True)
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_values_preserve_type_through_definitions() -> None:
    cql = """library ClinicalDefinitionTypes version '1.0.0'
using FHIR version '4.0.1'
valueset "Example VS": 'http://example.org/fhir/ValueSet/example' version '2026'
codesystem LOINC: 'http://loinc.org' version '2.74'
code "Systolic": '8480-6' from LOINC display 'Systolic blood pressure'
concept "Blood Pressure": { "Systolic" } display 'Blood pressure'
context Patient

define DirectVS: System.ValueSet{id: 'vs1'}
define DirectCS: System.CodeSystem{id: 'cs1'}
define DirectCode: Code '8480-6' from LOINC
define DirectConcept: "Blood Pressure"
define NamedVS: "Example VS"
define AliasVSIsVocabulary: DirectVS is Vocabulary
define AliasCSIsVocabulary: DirectCS is Vocabulary
define AliasCodeIsCode: DirectCode is Code
define AliasConceptIsConcept: DirectConcept is Concept
define AliasNamedVSIsVocabulary: NamedVS is Vocabulary
"""
    translated = translate_cql(cql)

    assert translated["DirectCode"].to_sql() == (
        '\'{"code":"8480-6","system":"http://loinc.org","version":"2.74"}\''
    )
    assert json.loads(translated["NamedVS"].value) == {
        "id": "http://example.org/fhir/ValueSet/example",
        "name": "Example VS",
        "version": "2026",
    }
    assert translated["AliasVSIsVocabulary"].to_sql() == "TRUE"
    assert translated["AliasCSIsVocabulary"].to_sql() == "TRUE"
    assert translated["AliasCodeIsCode"].to_sql() == "TRUE"
    assert translated["AliasConceptIsConcept"].to_sql() == "TRUE"
    assert translated["AliasNamedVSIsVocabulary"].to_sql() == "TRUE"

    population_sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "AliasVSIsVocabulary": "AliasVSIsVocabulary",
            "AliasCSIsVocabulary": "AliasCSIsVocabulary",
            "AliasCodeIsCode": "AliasCodeIsCode",
            "AliasConceptIsConcept": "AliasConceptIsConcept",
            "AliasNamedVSIsVocabulary": "AliasNamedVSIsVocabulary",
        },
    )

    patient = json.dumps({"resourceType": "Patient", "id": "p1"})
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient])
            assert con.execute(population_sql).fetchone() == (
                "p1",
                True,
                True,
                True,
                True,
                True,
            )
    finally:
        py.close()
        cpp.close()


def test_cql_fluent_valueset_argument_normalizes_structured_literal() -> None:
    context = SQLTranslationContext()
    translator = FluentFunctionTranslator(context, lightweight=True)
    structured_valueset = json.dumps(
        {
            "id": "http://example.org/fhir/ValueSet/vitals",
            "name": "Vitals",
        },
        separators=(",", ":"),
    )

    diagnosis_sql = translator._build_has_principal_diagnosis_of_ast(
        SQLIdentifier("enc_resource"),
        [SQLLiteral(structured_valueset)],
        context,
    ).to_sql()
    procedure_sql = translator._build_has_principal_procedure_of_ast(
        SQLIdentifier("enc_resource"),
        [SQLLiteral(structured_valueset)],
        context,
    ).to_sql()

    for sql in (diagnosis_sql, procedure_sql):
        assert "in_valueset" in sql
        assert "'http://example.org/fhir/ValueSet/vitals'" in sql
        assert "'{\"id\":" not in sql


def test_cql_clinical_type_execution_matches_cpp_and_python_fallback() -> None:
    translated = translate_cql(CLINICAL_TYPES_CQL)
    expected_scalars = {
        "ValueSetIsVocabulary": True,
        "CodeSystemIsVocabulary": True,
        "CodeIsCode": True,
        "CodeIsConcept": False,
        "CodeSelectorIsCode": True,
        "NamedCodeIsCode": True,
        "NamedConceptIsConcept": True,
        "NamedValueSetIsVocabulary": True,
        "ValueSetAsCodeSystem": None,
        "CodeAsConcept": None,
        "CodeAsVocabulary": None,
        "CodeSelectorAsConcept": None,
        "NamedCodeAsVocabulary": None,
        "NamedConceptAsVocabulary": None,
        "CodeEquivalentToContainingConcept": True,
        "ConceptEquivalentToContainingCode": True,
        "DisjointConceptEquivalent": False,
    }
    expected_json = {
        "ValueSetAsVocabulary": {"id": "123"},
        "CodeSystemAsVocabulary": {"id": "loinc"},
        "ToConceptSelector": {
            "codes": [{"code": "8480-6", "system": "http://loinc.org"}],
        },
        "ToConceptNamedCode": {
            "codes": [
                {
                    "code": "8480-6",
                    "system": "http://loinc.org",
                    "display": "Systolic blood pressure",
                }
            ],
        },
        "NamedConceptAsConcept": {
            "codes": [
                {
                    "code": "8480-6",
                    "system": "http://loinc.org",
                    "display": "Systolic blood pressure",
                }
            ],
            "display": "Blood pressure",
        },
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected in expected_scalars.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected,)
            assert cpp.execute(sql).fetchone() == (expected,)

        for name, expected in expected_json.items():
            sql = f"SELECT {translated[name].to_sql()}"
            py_value = py.execute(sql).fetchone()[0]
            cpp_value = cpp.execute(sql).fetchone()[0]
            assert json.loads(py_value) == expected
            assert json.loads(cpp_value) == expected
    finally:
        py.close()
        cpp.close()


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

    py = _python_valueset_connection()
    cpp = _cpp_valueset_connection()
    try:
        for sql, params in expressions:
            assert cpp.execute(sql, params).fetchone() == py.execute(sql, params).fetchone()
    finally:
        py.close()
        cpp.close()
