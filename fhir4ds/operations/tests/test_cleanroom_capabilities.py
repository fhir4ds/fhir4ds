"""CQL Cleanroom C1-U1: validate_resource + resource_schema capabilities
and translate-surface metadata (column_types, audit_mode/patient_ids).
"""

from __future__ import annotations

import pytest

from fhir4ds import create_connection
from fhir4ds.operations import (
    DatasetSpec,
    LibraryText,
    evaluate_library,
    resource_schema,
    translate_cql,
    validate_resource,
)

TYPED_LIB = """library Typed version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
define "Sums":
  Sum({1, 2, 3})
define "Pop":
  exists [Condition]
"""

PATIENTS = [
    {"resourceType": "Patient", "id": "p1", "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "gender": "male"},
]


def _main():
    return LibraryText(name="Typed", text=TYPED_LIB)


class TestValidateResource:
    def test_valid_patient(self):
        r = validate_resource({"resourceType": "Patient", "id": "p1"})
        assert r.ok and r.valid is True and r.passed is True
        assert r.resource_type == "Patient" and r.resource_id == "p1"
        assert r.diagnostics == ()
        d = r.to_dict()
        assert d["valid"] is True and d["resource_type"] == "Patient"

    def test_missing_resourcetype(self):
        r = validate_resource({"id": "p1"})
        assert r.valid is False
        assert r.diagnostics[0].code.value == "input_error"
        assert "resourceType" in r.diagnostics[0].message

    def test_bad_resourcetype_shape(self):
        r = validate_resource({"resourceType": 7})
        assert r.valid is False
        assert r.diagnostics[0].code.value == "input_error"

    def test_non_ascii_resourcetype_rejected(self):
        r = validate_resource({"resourceType": "Patiënt"})
        assert r.valid is False

    def test_bad_id_rejected(self):
        r = validate_resource({"resourceType": "Patient", "id": "bad id!"})
        assert r.valid is False
        assert "[A-Za-z0-9-." in r.diagnostics[0].message or "id" in r.diagnostics[0].message

    def test_id_length_boundary(self):
        ok64 = "a" * 64
        assert validate_resource({"resourceType": "Patient", "id": ok64}).valid is True
        assert validate_resource({"resourceType": "Patient", "id": ok64 + "a"}).valid is False

    def test_nan_rejected(self):
        r = validate_resource({"resourceType": "Patient", "id": "p1", "x": float("nan")})
        assert r.valid is False

    def test_lone_surrogate_rejected(self):
        r = validate_resource(
            {"resourceType": "Patient", "id": "p1", "family": "\ud800"}
        )
        assert r.valid is False

    def test_circular_reference_rejected(self):
        circular: dict = {"resourceType": "Patient", "id": "p1"}
        circular["self"] = circular
        r = validate_resource(circular)
        assert r.valid is False

    def test_non_dict_is_input_error(self):
        r = validate_resource("nope")
        assert r.ok is False
        assert r.diagnostics[0].code.value == "input_error"

    def test_validate_implies_loads(self):
        # The invariant: a resource that passes validate_resource loads
        # cleanly through load_dataset (same loader rules).
        from fhir4ds.operations import load_dataset

        resource = {"resourceType": "Patient", "id": "ok-1", "active": True}
        v = validate_resource(resource)
        assert v.valid is True
        conn = create_connection()
        loaded = load_dataset(DatasetSpec(resources=[resource]), conn)
        assert loaded.ok and loaded.total == 1


class TestResourceSchema:
    def test_patient_direct_children(self):
        r = resource_schema("Patient")
        assert r.ok
        names = {f["name"] for f in r.fields}
        assert {"id", "gender", "name", "deceased[x]", "generalPractitioner"} <= names
        # no nested paths (direct children only)
        assert all("." not in f["name"] for f in r.fields)

    def test_reference_targets(self):
        r = resource_schema("Patient")
        gp = next(f for f in r.fields if f["name"] == "generalPractitioner")
        assert gp["types"] == ["Reference"]
        assert set(gp["reference_targets"]) >= {"Organization", "Practitioner"}
        assert gp["cardinality"] == "0..*"

    def test_choice_element(self):
        r = resource_schema("Patient")
        deceased = next(f for f in r.fields if f["name"] == "deceased[x]")
        assert deceased["choice"] is True
        assert set(deceased["types"]) == {"boolean", "dateTime"}

    def test_system_string_normalized(self):
        r = resource_schema("Patient")
        pid = next(f for f in r.fields if f["name"] == "id")
        assert pid["types"] == ["string"]

    def test_unknown_type_not_found(self):
        r = resource_schema("NotAResource")
        assert r.ok is False
        assert r.diagnostics[0].code.value == "not_found"

    def test_valid_but_unshipped_type_not_found(self):
        # Medication is a real FHIR type but its SD is not bundled in the
        # wheel; the capability must say not_found, not crash.
        r = resource_schema("Medication")
        assert r.ok is False
        assert r.diagnostics[0].code.value == "not_found"

    def test_non_string_input(self):
        r = resource_schema(123)
        assert r.ok is False
        assert r.diagnostics[0].code.value == "input_error"

    def test_observation_choice(self):
        r = resource_schema("Observation")
        value = next(f for f in r.fields if f["name"] == "value[x]")
        assert value["choice"] is True
        assert "Quantity" in value["types"] and "CodeableConcept" in value["types"]


class TestTranslateMetadata:
    def test_column_types_and_definitions(self):
        main = _main()
        r = translate_cql([main], main)
        assert r.ok
        assert r.column_types["Sums"] == "Decimal"
        assert r.column_types["Pop"] == "Boolean"
        assert set(r.definitions) == {"Sums", "Pop"}
        d = r.to_dict()
        assert d["column_types"] == {"Sums": "Decimal", "Pop": "Boolean"}
        assert sorted(d["definitions"]) == ["Pop", "Sums"]

    def test_evaluate_column_types_no_longer_degenerate(self):
        conn = create_connection()
        r = evaluate_library(
            [_main()], _main(), DatasetSpec(resources=PATIENTS), conn,
        )
        assert r.ok
        assert r.column_types == {"Sums": "Decimal", "Pop": "Boolean"}

    def test_audit_mode_population_sql(self):
        main = _main()
        r = translate_cql([main], main, audit_mode="full", patient_ids=["p1"])
        assert r.ok
        assert "_patients" in r.sql
        assert "p1" in r.sql  # patient pushdown baked into the SQL
        assert "audit" in r.sql.lower()

    def test_audit_mode_column_types_still_present(self):
        main = _main()
        r = translate_cql([main], main, audit_mode="full")
        assert r.ok
        assert r.column_types["Pop"] == "Boolean"

    def test_patient_ids_without_audit_rejected(self):
        main = _main()
        r = translate_cql([main], main, patient_ids=["p1"])
        assert r.ok is False
        assert r.diagnostics[0].code.value == "evaluation_error"

    def test_default_is_cte_shape(self):
        main = _main()
        r = translate_cql([main], main)
        assert r.ok
        assert "_patients" not in r.sql
        assert r.sql.lstrip().upper().startswith("WITH")

    def test_population_mode_plain_booleans(self):
        main = _main()
        r = translate_cql([main], main, audit_mode="population")
        assert r.ok
        assert "_patients" in r.sql
        assert "audit" not in r.sql.lower()

    def test_population_mode_with_output_columns_aliases(self):
        main = _main()
        r = translate_cql(
            [main], main,
            audit_mode="population",
            output_columns={"X": "Sums", "Y": "Pop"},
        )
        assert r.ok
        assert "AS X" in r.sql and "AS Y" in r.sql
        assert "ORDER BY _pt.patient_id" in r.sql

    def test_population_mode_unknown_define_rejected(self):
        main = _main()
        r = translate_cql(
            [main], main,
            audit_mode="population",
            output_columns={"IPP": "Initial Population"},
        )
        assert r.ok is False
        assert "Initial Population" in r.diagnostics[0].message

    def test_full_mode_with_output_columns_and_pushdown(self):
        main = _main()
        r = translate_cql(
            [main], main,
            audit_mode="full",
            patient_ids=["p1"],
            output_columns={"POP": "Pop"},
        )
        assert r.ok
        assert "_patients" in r.sql and "'p1'" in r.sql
        assert "audit" in r.sql.lower() and "AS POP" in r.sql

    def test_invalid_audit_mode_rejected(self):
        main = _main()
        r = translate_cql([main], main, audit_mode="bogus")
        assert r.ok is False
        assert r.diagnostics[0].code.value == "evaluation_error"

    def test_output_columns_rejected_on_cte_shape(self):
        main = _main()
        r = translate_cql([main], main, output_columns={"IPP": "Initial Population"})
        assert r.ok is False
        assert r.diagnostics[0].code.value == "evaluation_error"


class TestParseAst:
    """C2-U2: parse_cql(include_ast=True) — AstPane surface."""

    AST_LIB = (
        "library Ast version '1.0.0'\n"
        "using FHIR version '4.0.1'\n"
        "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
        "define \"D1\":\n"
        "  1 + 2\n"
        "define \"Pop\":\n"
        "  exists [Condition]\n"
    )

    def test_default_excludes_ast(self):
        from fhir4ds.operations import parse_cql

        d = parse_cql(self.AST_LIB).to_dict()
        assert d["ok"] is True
        assert "ast" not in d

    def test_include_ast_exposes_statement_trees(self):
        from fhir4ds.operations import parse_cql

        d = parse_cql(self.AST_LIB, include_ast=True).to_dict()
        assert d["ok"] is True
        ast = d["ast"]
        assert ast["library"] == "Ast"
        assert set(ast["statements"].keys()) == {"D1", "Pop"}
        d1 = ast["statements"]["D1"]
        assert d1["kind"] == "BinaryExpression"
        # children carry operand fields
        kinds = d1["children"]
        assert kinds["operator"] == "+"

    def test_ast_absent_on_parse_failure(self):
        from fhir4ds.operations import parse_cql

        d = parse_cql(
            "library T version '1.0.0'\ndefine \"X\": 1 +\n", include_ast=True
        ).to_dict()
        assert d["ok"] is False
        assert "ast" not in d
        assert d["diagnostics"][0]["code"] == "parse_error"
