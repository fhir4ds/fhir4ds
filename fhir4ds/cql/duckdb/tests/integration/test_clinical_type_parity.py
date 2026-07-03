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


def test_cql_valueset_codesystems_clause_preserves_overrides() -> None:
    cql = """library ClinicalValueSetOverrides version '1.0.0'
using FHIR version '4.0.1'
codesystem "SNOMED-CT:2024": 'http://snomed.info/sct' version '2024'
codesystem LOINC: 'http://loinc.org' version '2.74'
valueset Diabetes: 'http://example.org/fhir/ValueSet/diabetes' version '2026'
  codesystems { "SNOMED-CT:2024", LOINC }
context Patient
define DiabetesValueSet: Diabetes
define DiabetesIsValueSet: Diabetes is ValueSet
define DiabetesIsVocabulary: Diabetes is Vocabulary
define DiabetesAsVocabulary: Diabetes as Vocabulary
"""
    library = parse_cql(cql)
    assert library.valuesets[0].codesystems == ["SNOMED-CT:2024", "LOINC"]

    translated = translate_cql(cql)
    expected = {
        "id": "http://example.org/fhir/ValueSet/diabetes",
        "name": "Diabetes",
        "version": "2026",
        "codesystems": [
            {
                "id": "http://snomed.info/sct",
                "name": "SNOMED-CT:2024",
                "version": "2024",
            },
            {"id": "http://loinc.org", "name": "LOINC", "version": "2.74"},
        ],
    }
    assert json.loads(translated["DiabetesValueSet"].value) == expected
    assert translated["DiabetesIsValueSet"].to_sql() == "TRUE"
    assert translated["DiabetesIsVocabulary"].to_sql() == "TRUE"

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        sql = translated["DiabetesAsVocabulary"].to_sql()
        assert json.loads(py.execute(f"SELECT {sql}").fetchone()[0]) == expected
        assert json.loads(cpp.execute(f"SELECT {sql}").fetchone()[0]) == expected
    finally:
        py.close()
        cpp.close()


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
            "display": "Systolic blood pressure",
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


def test_cql_clinical_parameter_types_preserve_vocabulary_hierarchy() -> None:
    cql = """library ClinicalParameterTypes version '1.0.0'
using FHIR version '4.0.1'
valueset VS: 'http://example.org/fhir/ValueSet/vs'
codesystem CS: 'http://example.org/CodeSystem/cs'
code A: 'a' from CS display 'A'
concept CA: { A } display 'Concept A'
context Patient
parameter PVS ValueSet default VS
parameter PCS CodeSystem default CS
parameter PC Code default A
parameter PCC Concept default CA
define VSIsValueSet: PVS is ValueSet
define VSIsVocabulary: PVS is Vocabulary
define VSAsVocabulary: PVS as Vocabulary
define CSIsCodeSystem: PCS is CodeSystem
define CSIsVocabulary: PCS is Vocabulary
define CSAsVocabulary: PCS as Vocabulary
define CodeIsVocabulary: PC is Vocabulary
define ConceptIsVocabulary: PCC is Vocabulary
define CodeAsVocabulary: PC as Vocabulary
define ConceptAsVocabulary: PCC as Vocabulary
"""
    translated = translate_cql(cql)
    expected_scalars = {
        "VSIsValueSet": True,
        "VSIsVocabulary": True,
        "CSIsCodeSystem": True,
        "CSIsVocabulary": True,
        "CodeIsVocabulary": False,
        "ConceptIsVocabulary": False,
        "CodeAsVocabulary": None,
        "ConceptAsVocabulary": None,
    }
    expected_json = {
        "VSAsVocabulary": {"id": "http://example.org/fhir/ValueSet/vs", "name": "VS"},
        "CSAsVocabulary": {"id": "http://example.org/CodeSystem/cs", "name": "CS"},
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected in expected_scalars.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected,), name
            assert cpp.execute(sql).fetchone() == (expected,), name
        for name, expected in expected_json.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert json.loads(py.execute(sql).fetchone()[0]) == expected
            assert json.loads(cpp.execute(sql).fetchone()[0]) == expected
    finally:
        py.close()
        cpp.close()


def test_cql_to_concept_list_display_and_validation_match_backends() -> None:
    cql = """library ClinicalToConcept version '1.0.0'
using FHIR version '4.0.1'
codesystem CS: 'http://example.org/CodeSystem/cs'
context Patient
define OneCode: ToConcept(Code 'a' from CS display 'A display')
define CodeList: ToConcept({ Code 'a' from CS display 'A display', Code 'b' from CS })
define BadQuantityShape: ToConcept(System.Quantity { value: 5, unit: 'mg' })
"""
    translated = translate_cql(cql)
    expected_one = {
        "codes": [
            {"code": "a", "system": "http://example.org/CodeSystem/cs", "display": "A display"}
        ],
        "display": "A display",
    }
    expected_list = {
        "codes": [
            {"code": "a", "system": "http://example.org/CodeSystem/cs", "display": "A display"},
            {"code": "b", "system": "http://example.org/CodeSystem/cs"},
        ]
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            assert json.loads(con.execute(f"SELECT {translated['OneCode'].to_sql()}").fetchone()[0]) == expected_one
            assert json.loads(con.execute(f"SELECT {translated['CodeList'].to_sql()}").fetchone()[0]) == expected_list
            assert con.execute(f"SELECT {translated['BadQuantityShape'].to_sql()}").fetchone() == (None,)
            assert json.loads(
                con.execute(
                    "SELECT ToConcept(['{\"code\":\"x\"}', '{\"code\":\"y\",\"display\":\"Y\"}'])"
                ).fetchone()[0]
            ) == {"codes": [{"code": "x"}, {"code": "y", "display": "Y"}]}
            assert con.execute("SELECT ToConcept('{\"value\":5,\"unit\":\"mg\"}')").fetchone() == (None,)
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


def test_cql_clinical_assertion_chains_preserve_concrete_runtime_type() -> None:
    cql = """library ClinicalExplorerChains version '1.0.0'
using FHIR version '4.0.1'
codesystem CS: 'http://example.org/cs' version 'v1'
valueset VS: 'http://example.org/vs' version 'v2' codesystems { CS }
code A: 'a' from CS display 'A'
code B: 'b' from CS display 'B'
concept CA: { A, B } display 'AB'
context Patient

define VSAsVocab: VS as Vocabulary
define VSAsVocabIsVS: VSAsVocab is ValueSet
define VSAsVocabAsVS: VSAsVocab as ValueSet
define CSAsVocab: CS as Vocabulary
define CSAsVocabIsCS: CSAsVocab is CodeSystem
define CSAsVocabAsCS: CSAsVocab as CodeSystem
define ConceptAsAny: CA as Any
define ConceptAsAnyIsConcept: ConceptAsAny is Concept
define ConceptAsAnyAsConcept: ConceptAsAny as Concept
define CodeAsAny: A as Any
define CodeAsAnyIsCode: CodeAsAny is Code
define CodeAsAnyAsCode: CodeAsAny as Code
define ConceptIntersectEq:
  CA ~ Concept { codes: { Code { code: 'b', system: 'http://example.org/cs' } } }
define ConceptIntersectNotEq:
  CA !~ Concept { codes: { Code { code: 'b', system: 'http://example.org/cs' } } }
define ToConceptMixed: ToConcept({ A, System.Quantity { value: 5, unit: 'mg' } })
define ToConceptConcept: ToConcept(CA)
"""
    translated = translate_cql(cql)
    expected_vs = {
        "id": "http://example.org/vs",
        "name": "VS",
        "version": "v2",
        "codesystems": [{"id": "http://example.org/cs", "name": "CS", "version": "v1"}],
    }
    expected_cs = {"id": "http://example.org/cs", "name": "CS", "version": "v1"}
    expected_concept = {
        "codes": [
            {"code": "a", "system": "http://example.org/cs", "version": "v1", "display": "A"},
            {"code": "b", "system": "http://example.org/cs", "version": "v1", "display": "B"},
        ],
        "display": "AB",
    }
    expected_code = {
        "code": "a",
        "system": "http://example.org/cs",
        "version": "v1",
        "display": "A",
    }
    expected_scalars = {
        "VSAsVocabIsVS": True,
        "CSAsVocabIsCS": True,
        "ConceptAsAnyIsConcept": True,
        "CodeAsAnyIsCode": True,
        "ConceptIntersectEq": True,
        "ConceptIntersectNotEq": False,
        "ToConceptMixed": None,
        "ToConceptConcept": None,
    }
    expected_json = {
        "VSAsVocab": expected_vs,
        "VSAsVocabAsVS": expected_vs,
        "CSAsVocab": expected_cs,
        "CSAsVocabAsCS": expected_cs,
        "ConceptAsAny": expected_concept,
        "ConceptAsAnyAsConcept": expected_concept,
        "CodeAsAny": expected_code,
        "CodeAsAnyAsCode": expected_code,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected in expected_scalars.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected,), name
            assert cpp.execute(sql).fetchone() == (expected,), name

        for name, expected in expected_json.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert json.loads(py.execute(sql).fetchone()[0]) == expected, name
            assert json.loads(cpp.execute(sql).fetchone()[0]) == expected, name
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_equivalence_with_null_operand_is_spec_strict() -> None:
    """CQL 1.5.3 §Equivalent (Code/Concept) — “this operator will always return
    true or false, even if either or both of its arguments are null, or contain
    null components.” A null operand must NOT propagate NULL through the
    equivalence result.

    Regression coverage for an issue where ``(null as Code)`` translated to a
    runtime JSON-shape CASE wrapper that always returned NULL, defeating the
    existing ``isinstance(resource_expr, SQLNull)`` guard at the equivalence
    call site.
    """
    cql = """library ClinicalNullEquiv version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
code "Sys": '8480-6' from LOINC display 'Systolic'
concept "BP": { "Sys" } display 'BP'
context Patient
define CodeEquivNullRight: Code { code: '8480-6', system: 'S' } ~ (null as Code)
define CodeEquivNullLeft: (null as Code) ~ Code { code: '8480-6', system: 'S' }
define ConceptEquivNullRight: "BP" ~ (null as Concept)
define ConceptEquivNullLeft: (null as Concept) ~ "BP"
define CodeNotEquivNullRight: Code { code: '8480-6', system: 'S' } !~ (null as Code)
define CodeNotEquivNullLeft: (null as Code) !~ Code { code: '8480-6', system: 'S' }
define ConceptNotEquivNullRight: "BP" !~ (null as Concept)
"""
    translated = translate_cql(cql)
    expected_scalars = {
        "CodeEquivNullRight": False,
        "CodeEquivNullLeft": False,
        "ConceptEquivNullRight": False,
        "ConceptEquivNullLeft": False,
        "CodeNotEquivNullRight": True,
        "CodeNotEquivNullLeft": True,
        "ConceptNotEquivNullRight": True,
    }

    py = _python_valueset_connection()
    cpp = _cpp_valueset_connection()
    try:
        for name, expected in expected_scalars.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected,), name
            assert cpp.execute(sql).fetchone() == (expected,), name
    finally:
        py.close()
        cpp.close()


def test_cql_clinical_equivalence_folds_define_alias_operands_cql02_explorer() -> None:
    """CQL-02 EXPLORER fresh run (2026-06-30) found that clinical equivalence
    involving a top-level ``define`` alias wrapping a Code/Concept literal
    was not folded at translation time. The translator emitted a generic SQL
    CASE whose final ELSE arm was raw JSON string equality, so a Code JSON
    shape (``{"code":...,"system":...}``) was compared against a Concept JSON
    shape (``{"codes":[...]}``) and always evaluated to False.

    Spec citation: CQL 1.5.3 Appendix B > Clinical Operators > Equivalent —
    ``~(left Code, right Concept) Boolean`` and ``~(left Concept, right Code)
    Boolean`` are explicit signatures; Concept equivalence is a non-empty
    intersection of the codes in each Concept.

    Regression coverage for the define-alias path (the named path
    ``"Systolic" ~ "Blood Pressure"`` is already covered by
    ``test_cql_clinical_type_translation_is_spec_strict``).
    """
    cql = """library Cql02ExplorerDefineAlias version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
context Patient
define C: Code '8480-6' from LOINC
define Conc: Concept { codes: { Code '8480-6' from LOINC } }
define Disjoint: Concept { codes: { Code '9999-9' from LOINC } }
define CodeEquivConcept: C ~ Conc
define ConceptEquivCode: Conc ~ C
define CodeEquivDisjointConcept: C ~ Disjoint
define CodeNotEquivDisjointConcept: C !~ Disjoint
define CodeEquivCode_Same: Code '8480-6' from LOINC ~ Code '8480-6' from LOINC
define ConceptEquivConcept_Same: Conc ~ Conc
"""
    translated = translate_cql(cql)

    # Translation-time folding: the generated SQL should be the literal TRUE/FALSE
    assert translated["CodeEquivConcept"].to_sql() == "TRUE"
    assert translated["ConceptEquivCode"].to_sql() == "TRUE"
    assert translated["CodeEquivDisjointConcept"].to_sql() == "FALSE"
    assert translated["CodeNotEquivDisjointConcept"].to_sql() == "TRUE"
    assert translated["CodeEquivCode_Same"].to_sql() == "TRUE"
    assert translated["ConceptEquivConcept_Same"].to_sql() == "TRUE"

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name in (
            "CodeEquivConcept",
            "ConceptEquivCode",
            "CodeEquivDisjointConcept",
            "CodeNotEquivDisjointConcept",
            "CodeEquivCode_Same",
            "ConceptEquivConcept_Same",
        ):
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == cpp.execute(sql).fetchone(), name
    finally:
        py.close()
        cpp.close()
