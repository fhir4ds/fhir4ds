"""Capability unit tests: parse/translate/fhirpath/dataset/evaluate/tests/explain."""

from __future__ import annotations

import json
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

    def test_translate_cache_hit_and_isolation(self):
        """S28 (perf B): identical inputs return the SAME cached result;
        output_columns/parameters changes get distinct entries; failures
        are never cached."""
        from fhir4ds.operations.capabilities.translate import (
            _TRANSLATE_CACHE,
            _translate_cache_key,
        )

        main = _main()
        _TRANSLATE_CACHE.clear()
        r1 = translate_cql(
            [main], main,
            audit_mode="population",
            output_columns={"Initial Population": "Initial Population"},
        )
        assert r1.ok
        r2 = translate_cql(
            [main], main,
            audit_mode="population",
            output_columns={"Initial Population": "Initial Population"},
        )
        assert r2.ok and r2 is r1  # cache hit returns the stored object

        # A failing translation (unknown include) is NOT cached.
        bad = LibraryText(
            name="Bad", text="library Bad\nusing FHIR\ninclude Nope\ndefine \"X\": 1"
        )
        rb = translate_cql([bad], bad)
        assert not rb.ok
        key = _translate_cache_key([bad], bad, "none", None, None, None)
        assert key not in _TRANSLATE_CACHE

        # Different output_columns -> distinct cache entries.
        r3 = translate_cql(
            [main], main,
            audit_mode="population",
            output_columns={"Has Name": "Has Name"},
        )
        assert r3.ok and r3 is not r1

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

    def test_context_patient_property_leaf(self):
        """S22f-promotion: derived defines get Patient-property leaves
        FROM THE TRANSLATOR (audit_patient_property macro — seam A).

        AgeInYearsAt derives from the context Patient.birthDate — no
        contributing resource exists, so the evidence would render "no
        contributing resources". The macro-sourced leaf names the
        Patient row + the referenced property + its value. (The S22f
        explain-seam backfill is retired; this asserts the native path.)
        """
        cql = (
            "library AgeEv version '1.0.0'\n"
            "using FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "context Patient\n\n"
            'define "InAgeRange":\n'
            "  AgeInYearsAt(@2024-01-01) >= 18\n\n"
            'define "HasEnc":\n'
            "  exists([Encounter] E where E.status = 'finished')\n"
        )
        resources = [
            {"resourceType": "Patient", "id": "a1", "birthDate": "2000-05-05"},
            {
                "resourceType": "Encounter",
                "id": "e1",
                "status": "finished",
                "subject": {"reference": "Patient/a1"},
            },
        ]
        conn = create_connection()
        main = LibraryText(name="AgeEv", text=cql)
        ev = explain_patient(
            [main], main, DatasetSpec(resources=resources), "a1", conn
        )
        assert ev.ok
        by_col = {d["column"]: d["evidence"] for d in ev.definitions}
        # Resource-backed define keeps its retrieve leaf.
        assert by_col["HasEnc"][0]["target"] == "Encounter/e1"
        # The DERIVED define carries the synthesized context-patient leaf.
        leaf = by_col["InAgeRange"][0]
        assert leaf["target"] == "Patient/a1"
        assert leaf["attribute"] == "birthDate"
        assert leaf["value"] == "2000-05-05"
        assert leaf["operator"] == "derived"

    def test_context_patient_property_leaf_non_boolean_defines(self):
        """S26 (item 7): NON-boolean property-derived defines carry a
        property leaf at the explain seam.

        `define "AgeYears": AgeInYearsAt(@2026-01-01)` is an Integer
        define — the audit-demote doctrine keeps audit structs out of
        its SQL (binder safety), and pre-S26 the drill-in rendered "no
        evidence recorded". The explain seam now attaches the property
        leaf from the exported patient_property_defs lineage: the
        define's evaluated value + the property it derives from.
        """
        cql = (
            "library AgeInt version '1.0.0'\n"
            "using FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "context Patient\n\n"
            'define "AgeYears":\n'
            "  AgeInYearsAt(@2026-01-01)\n\n"
            'define "AgeNow":\n'
            "  AgeInYears()\n"
        )
        resources = [
            {"resourceType": "Patient", "id": "a1", "birthDate": "1980-05-05"},
        ]
        conn = create_connection()
        main = LibraryText(name="AgeInt", text=cql)
        ev = explain_patient(
            [main], main, DatasetSpec(resources=resources), "a1", conn
        )
        assert ev.ok
        by_col = {d["column"]: d for d in ev.definitions}
        assert "AgeYears" in by_col and "AgeNow" in by_col
        years = by_col["AgeYears"]
        # The result is the raw evaluated value (VARCHAR-transported),
        # not coerced to bool.
        assert years["result"] == "45"
        leaf = years["evidence"][0]
        assert leaf["target"] == "Patient/a1"
        assert leaf["attribute"] == "birthDate"
        assert leaf["value"] == "45"
        assert leaf["operator"] == "derived"
        assert leaf["threshold"] == "CalculateAgeInYearsAt"
        now = by_col["AgeNow"]
        assert str(now["result"]).isdigit() and int(now["result"]) >= 46
        assert now["evidence"][0]["threshold"] == "AgeInYears"

    def test_context_patient_leaf_review_guards(self):
        """S22f-promotion review fixes — the three merge blockers.

        1. Stale marker: a REUSED translator/context must not carry the
           property marker into a later same-named define (binder error
           when _patients omits birth_date).
        2. Query-scope age calls (exists([Obs] O where AgeInYearsAt(..)))
           keep their pre-campaign behavior — no invalid correlation.
        3. Included-library age defines carry the leaf (prefixed-key
           propagation + audit-inheriting child translator).
        4. Seam B: patient-row comparisons fill the audit_comparison
           target.
        5. Partial-birthDate spelling parity (gate checklist).
        """
        from fhir4ds.cql import parse_cql as engine_parse
        from fhir4ds.cql.translator.translator import CQLToSQLTranslator

        conn = create_connection()
        # 1. Stale marker across a reused translator.
        t = CQLToSQLTranslator(connection=conn, audit_mode=True)
        t.translate_library(
            engine_parse(
                "library A version '1.0.0'\nusing FHIR version '4.0.1'\n"
                "context Patient\ndefine \"D1\": AgeInYearsAt(@2024-01-01) >= 18\n"
            )
        )
        t._context.clear()
        r_b = t.translate_library(
            engine_parse(
                "library B version '1.0.0'\nusing FHIR version '4.0.1'\n"
                "context Patient\n"
                "define \"D1\": exists([Encounter] E where E.status = 'finished')\n"
            )
        )
        sql_b = json.dumps({k: str(v) for k, v in r_b.items()})
        assert "audit_patient_property" not in sql_b

        resources = [
            {"resourceType": "Patient", "id": "g1", "birthDate": "2000-05-05",
             "gender": "female"},
            {"resourceType": "Encounter", "id": "ge1", "status": "finished",
             "subject": {"reference": "Patient/g1"}},
        ]
        # 2. Query-scope age call — executes, retrieve evidence kept.
        mixed = (
            "library MQ version '1.0.0'\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "context Patient\n\n"
            'define "Mixed": exists([Encounter] O where AgeInYearsAt(@2024-01-01) >= 18)\n'
        )
        main = LibraryText(name="MQ", text=mixed)
        ev = explain_patient(
            [main], main, DatasetSpec(resources=resources), "g1", conn
        )
        assert ev.ok
        leaf = next(d for d in ev.definitions if d["column"] == "Mixed")["evidence"]
        assert leaf and leaf[0]["target"] == "Encounter/ge1"

        # 3. Included-library define carries the leaf.
        inc = (
            "library IH version '1.0.0'\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "context Patient\n\n"
            'define "AgeD": AgeInYearsAt(@2024-01-01) >= 18\n'
        )
        use = (
            "library IU version '1.0.0'\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "include IH version '1.0.0' called IH\n"
            "context Patient\n\n"
            'define "UsesAge": IH.AgeD\n'
        )
        libs = [LibraryText(name="IH", text=inc), LibraryText(name="IU", text=use)]
        ev2 = explain_patient(
            libs, LibraryText(name="IU", text=use),
            DatasetSpec(resources=resources), "g1", conn,
        )
        assert ev2.ok
        leaf2 = next(d for d in ev2.definitions if d["column"] == "UsesAge")["evidence"]
        assert leaf2 and leaf2[0]["target"] == "Patient/g1"
        assert leaf2[0]["attribute"] == "birthDate"

        # 4. Seam B: patient-row comparison target fill.
        gender_lib = (
            "library GB version '1.0.0'\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "context Patient\n\n"
            'define "Female": Patient.gender = \'female\'\n'
        )
        gmain = LibraryText(name="GB", text=gender_lib)
        ev3 = explain_patient(
            [gmain], gmain, DatasetSpec(resources=resources), "g1", conn
        )
        leaf3 = next(d for d in ev3.definitions if d["column"] == "Female")["evidence"]
        assert leaf3 and leaf3[0]["target"] == "Patient/g1"
        assert leaf3[0]["attribute"] == "gender"

        # 5. Partial-birthDate spelling parity through the macro path.
        partial = [
            {"resourceType": "Patient", "id": "pf", "birthDate": "2000-05-05"},
            {"resourceType": "Patient", "id": "pm", "birthDate": "1975-03"},
            {"resourceType": "Patient", "id": "py", "birthDate": "1980"},
        ]
        pmain = LibraryText(name="AgeEv", text=(
            "library AgeEv version '1.0.0'\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "context Patient\n\n"
            'define "InAgeRange": AgeInYearsAt(@2024-01-01) >= 18\n'
        ))
        expected = {"pf": "2000-05-05", "pm": "1975-03", "py": "1980"}
        for pid, want in expected.items():
            evp = explain_patient(
                [pmain], pmain, DatasetSpec(resources=partial), pid, conn
            )
            leafp = next(
                d for d in evp.definitions if d["column"] == "InAgeRange"
            )["evidence"]
            assert leafp and leafp[0]["value"] == want, (pid, leafp)


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
