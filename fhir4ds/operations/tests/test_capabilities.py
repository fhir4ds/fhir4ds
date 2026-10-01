"""Capability unit tests: parse/translate/fhirpath/dataset/evaluate/tests/explain."""

from __future__ import annotations

from fhir4ds import create_connection
from fhir4ds.operations import (
    DatasetSpec,
    LibraryText,
    TestCase,
    TestsInput,
    evaluate_library,
    evaluate_snippet,
    explain_patient,
    fhirpath_eval,
    load_dataset,
    parse_cql,
    run_tests,
    translate_cql,
)

SIMPLE_LIB = """library Simple version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.4.000' called FHIRHelpers
define "Initial Population":
  exists([Patient] P where P.gender = 'female')
define "Has Name":
  exists([Patient] P where P.name.first().given.first() is not null)
"""

PATIENTS = [
    {"resourceType": "Patient", "id": "p1", "gender": "female",
     "name": [{"given": ["Ann"]}]},
    {"resourceType": "Patient", "id": "p2", "gender": "male",
     "name": [{"given": ["Bob"]}]},
    {"resourceType": "Patient", "id": "p3", "gender": "female"},
]


def _main():
    return LibraryText(name="Simple", text=SIMPLE_LIB)


class TestParseCapability:
    def test_ok(self):
        r = parse_cql(SIMPLE_LIB)
        assert r.ok and r.library_name == "Simple"
        assert "Initial Population" in r.definition_names
        assert "Measurement Period" not in r.parameter_names
        kinds = {d["kind"] for d in r.declarations}
        assert "include" in kinds

    def test_bad_cql_is_parse_diagnostic(self):
        r = parse_cql("library Broken\ndefine :")
        assert not r.ok
        assert r.diagnostics[0].code.value == "parse_error"


class TestTranslateCapability:
    def test_ok_emits_sql(self):
        main = _main()
        r = translate_cql([main], main)
        assert r.ok and r.sql.lstrip().upper().startswith("WITH")

    def test_missing_include_is_not_found(self):
        main = LibraryText(
            name="Lonely",
            text="library Lonely\nusing FHIR\ninclude NopeLib called N\ndefine \"X\": 1",
        )
        r = translate_cql([main], main)
        assert not r.ok
        assert r.diagnostics[0].code.value == "not_found"
        assert "NopeLib" in r.diagnostics[0].message


class TestFhirpathCapability:
    def test_eval(self):
        r = fhirpath_eval("name.given", PATIENTS[0])
        assert r.ok and r.results == ["Ann"]

    def test_input_errors(self):
        assert fhirpath_eval("", {}).diagnostics[0].code.value == "input_error"
        assert fhirpath_eval("a", [1]).diagnostics[0].code.value == "input_error"


class TestDatasetCapability:
    def test_inline_load_counts(self):
        conn = create_connection()
        r = load_dataset(DatasetSpec(resources=PATIENTS), conn)
        assert r.ok and r.resource_counts == {"Patient": 3} and r.total == 3

    def test_bad_resource_is_dataset_diag(self):
        conn = create_connection()
        r = load_dataset(DatasetSpec(resources=[{"nada": 1}]), conn)
        assert not r.ok

    def test_valueset_paths_loads_codes_qa026(self):
        """QA-026 (iter 18): valueset_paths must read the JSON file and load
        its ValueSet codes — the branch used to pass the path string straight
        to load_valuesets (TypeError: valuesets must be a list, got str)."""
        import json
        import tempfile
        from pathlib import Path

        vs = {
            "resourceType": "ValueSet",
            "id": "qa026",
            "url": "http://example.org/ValueSet/qa026",
            "expansion": {
                "contains": [
                    {"system": "http://loinc.org", "code": "8480-6"},
                    {"system": "http://loinc.org", "code": "8462-4"},
                ]
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vs.json"
            path.write_text(json.dumps(vs))
            conn = create_connection()
            r = load_dataset(DatasetSpec(valueset_paths=[str(path)]), conn)
        assert r.ok
        n = conn.execute(
            "SELECT count(*) FROM valueset_codes WHERE valueset_url = ?",
            ["http://example.org/ValueSet/qa026"],
        ).fetchone()[0]
        assert n == 2

    def test_valueset_paths_bad_json_is_typed_diag_qa026(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vs.json"
            path.write_text("{not json")
            conn = create_connection()
            r = load_dataset(DatasetSpec(valueset_paths=[str(path)]), conn)
        assert not r.ok
        assert r.diagnostics


class TestEvaluateCapability:
    def test_rows_and_types(self):
        conn = create_connection()
        r = evaluate_library(
            [_main()], _main(), DatasetSpec(resources=PATIENTS), conn,
            output_columns={"IPP": "Initial Population", "NAME": "Has Name"},
        )
        assert r.ok and r.patient_count == 3
        by_id = {row["patient_id"]: row for row in r.rows}
        assert by_id["p1"]["IPP"] is True and by_id["p2"]["IPP"] is False
        assert by_id["p3"]["NAME"] is False

    def test_emit_sql(self):
        conn = create_connection()
        r = evaluate_library(
            [_main()], _main(), DatasetSpec(resources=PATIENTS[:1]), conn,
            emit_sql=True,
        )
        assert r.ok and r.sql and "WITH" in r.sql.upper()

    def test_dataset_none_uses_loaded_state(self):
        conn = create_connection()
        load_dataset(DatasetSpec(resources=PATIENTS), conn)
        r = evaluate_library([_main()], _main(), None, conn,
                              output_columns={"IPP": "Initial Population"})
        assert r.ok and r.patient_count == 3


class TestEvaluateSnippetCapability:
    def test_snippet_column_narrowing(self):
        conn = create_connection()
        r = evaluate_snippet(
            [_main()], _main(), "exists [Patient]",
            DatasetSpec(resources=PATIENTS), conn,
        )
        assert r.ok
        assert r.columns == ("patient_id", "snippet")
        by_id = {row["patient_id"]: row for row in r.rows}
        assert by_id["p1"]["snippet"] is True
        assert by_id["p2"]["snippet"] is True

    def test_non_boolean_snippet_value(self):
        conn = create_connection()
        r = evaluate_snippet(
            [_main()], _main(), "'hello'",
            DatasetSpec(resources=PATIENTS[:1]), conn,
        )
        assert r.ok
        assert r.rows[0]["snippet"] == "hello"

    def test_empty_snippet_is_input_error(self):
        conn = create_connection()
        r = evaluate_snippet([_main()], _main(), "   ", None, conn)
        assert not r.ok
        assert r.diagnostics[0].code.value == "input_error"

    def test_broken_snippet_diagnostics_shift_back(self):
        # SIMPLE_LIB is 7 lines; the broken snippet lands on appended
        # lines ~9-11 — after the offset shift the reported line must
        # point inside the selection (single digits), not the appended
        # region.
        conn = create_connection()
        r = evaluate_snippet(
            [_main()], _main(), "exists [Patient] where",
            DatasetSpec(resources=PATIENTS), conn,
        )
        assert not r.ok
        assert r.diagnostics, "expected a diagnostic for the broken snippet"
        loc = r.diagnostics[0].location
        if loc is not None and loc.start_line is not None:
            assert loc.start_line <= 3, (
                f"snippet diagnostic not shifted back: L{loc.start_line}"
            )


class TestRunTestsCapability:
    def test_mixed_cases(self):
        conn = create_connection()
        cases = TestsInput(cases=(
            TestCase(patient="p1", population="Initial Population", expect=True),
            TestCase(patient="p2", population="Initial Population", expect=False),
            TestCase(patient="p3", define="Has Name", expect=False),
            TestCase(patient="zz", population="Initial Population", expect=True),
        ))
        v = run_tests([_main()], _main(), DatasetSpec(resources=PATIENTS), cases, conn)
        assert v.ok is True and v.passed is False
        assert v.tests["passed"] == 3 and v.tests["failed"] == 1
        assert v.tests["failures"][0]["patient"] == "zz"

    def test_all_pass(self):
        conn = create_connection()
        cases = TestsInput(cases=(
            TestCase(patient="p1", population="Initial Population", expect=True),
        ))
        v = run_tests([_main()], _main(), DatasetSpec(resources=PATIENTS), cases, conn)
        assert v.passed is True


class TestExplainCapability:
    def test_pushdown_and_populations(self):
        conn = create_connection()
        ev = explain_patient(
            [_main()], _main(), DatasetSpec(resources=PATIENTS), "p1", conn,
            output_columns={"IPP": "Initial Population", "NAME": "Has Name"},
        )
        assert ev.ok and ev.patient_id == "p1"
        assert ev.populations == {"IPP": True, "NAME": True}

    def test_unknown_patient_not_found(self):
        conn = create_connection()
        ev = explain_patient(
            [_main()], _main(), DatasetSpec(resources=PATIENTS), "ghost", conn,
        )
        assert not ev.ok
        assert ev.diagnostics[0].code.value == "not_found"


class TestExplicitOverridesBundled:
    def test_inline_version_wins(self):
        inline = LibraryText(
            name="FHIRHelpers",
            text="library FHIRHelpers version '0.0.1'\nusing FHIR version '4.0.1'",
        )
        main = LibraryText(
            name="UsesFH",
            text="library UsesFH\nusing FHIR\ninclude FHIRHelpers called FHIRHelpers\ndefine \"X\": 1",
        )
        r = translate_cql([main, inline], main)
        assert r.ok  # inline override resolved, no NOT_FOUND
