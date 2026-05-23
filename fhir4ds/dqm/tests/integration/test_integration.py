"""End-to-end integration tests for MeasureEvaluator with DuckDB."""

import base64
import json
from pathlib import Path

import duckdb
import pytest

from fhir4ds.dqm import FileArtifactResolver, MeasureEvaluator, MeasureParser

TESTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "tests"
DQM_2026 = TESTS_DIR / "data" / "dqm-content-qicore-2026" / "input"
ECQ_2025 = TESTS_DIR / "data" / "ecqm-content-qicore-2025"


def _load_test_data(conn, test_dir: Path):
    """Load FHIR test data from a test case directory into DuckDB."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            patient_ref VARCHAR,
            resourceType VARCHAR,
            resource JSON
        )
    """)
    for json_file in sorted(test_dir.glob("*.json")):
        data = json.loads(json_file.read_text())
        rt = data.get("resourceType", "")
        rid = data.get("id", "")
        # Derive patient reference
        if rt == "Patient":
            patient_ref = f"Patient/{rid}"
        elif "subject" in data:
            ref = data["subject"]
            if isinstance(ref, dict):
                patient_ref = ref.get("reference", "")
            else:
                patient_ref = str(ref)
        else:
            patient_ref = None

        if patient_ref:
            conn.execute(
                "INSERT INTO resources VALUES (?, ?, ?)",
                [patient_ref, rt, json.dumps(data)],
            )


@pytest.fixture
def conn():
    """Create an in-memory DuckDB connection with FHIRPath UDFs registered."""
    con = duckdb.connect(":memory:")
    try:
        from fhir4ds.fhirpath.duckdb import register_fhirpath
        register_fhirpath(con)
    except ImportError:
        pass
    try:
        from fhir4ds.cql.duckdb import register
        register(con, include_fhirpath=False)
    except ImportError:
        pass
    yield con
    con.close()


class TestMeasureEvaluatorBasicIntegration:
    """Test with synthetically created data."""

    def test_evaluate_simple_measure(self, conn, tmp_path):
        """Test evaluation of a simple hand-crafted measure."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"})
        loader.load_resource({
            "resourceType": "Encounter", "id": "e1",
            "subject": {"reference": "Patient/p1"}, "status": "finished",
            "class": {"code": "AMB"}, "type": [{"coding": [{"code": "99213"}]}],
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "test-measure",
            "library": ["http://example.com/Library/TestMeasure"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        cql_text = '''library TestMeasure
using FHIR version '4.0.1'
context Patient
define "Qualifying Encounters":
    [Encounter] E where E.status = 'finished'
define "Initial Population":
    exists "Qualifying Encounters"
'''
        cql_path = tmp_path / "test_measure_e2e.cql"
        cql_path.write_text(cql_text)

        evaluator = MeasureEvaluator(conn)
        result = evaluator.evaluate(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
        )
        df = result.dataframe
        assert "patient_id" in df.columns
        assert len(df) >= 1

    def test_compiled_measure_reuses_sql_with_target_patient_table(self, conn, tmp_path):
        """Compiled target-table SQL should run for different patient batches."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({
            "resourceType": "Patient",
            "id": "p1",
            "gender": "male",
            "birthDate": "1990-01-01",
        })
        loader.load_resource({
            "resourceType": "Patient",
            "id": "p2",
            "gender": "female",
            "birthDate": "1990-01-01",
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "compiled-target-measure",
            "library": ["http://example.com/Library/CompiledTarget"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        cql_text = '''library CompiledTarget
using FHIR version '4.0.1'
context Patient
define "Initial Population":
    Patient.gender = 'male'
'''
        cql_path = tmp_path / "compiled_target.cql"
        cql_path.write_text(cql_text)

        evaluator = MeasureEvaluator(conn)
        compiled = evaluator.compile_measure(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
            patient_scope="target_table",
        )
        cached = evaluator.compile_measure(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
            patient_scope="target_table",
        )
        assert cached is compiled
        sql = compiled.groups[0].sql
        assert "_fhir4ds_target_patients" in sql
        assert "_patient_demographics" not in sql
        assert "'p1'" not in sql
        assert "'p2'" not in sql

        p1_result = evaluator.execute_compiled_measure(compiled, patient_ids=["p1"])
        p2_result = evaluator.execute_compiled_measure(compiled, patient_ids=["p2"])

        p1_rows = p1_result.dataframe.set_index("patient_id")
        p2_rows = p2_result.dataframe.set_index("patient_id")
        assert bool(p1_rows.loc["p1", "initial_population"]) is True
        assert bool(p2_rows.loc["p2", "initial_population"]) is False
        assert compiled.groups[0].prepared is True
        metrics = evaluator.compiled_measure_metrics()
        assert metrics["cache_hits"] == 1
        assert metrics["cache_misses"] == 1
        assert metrics["compile_count"] == 1
        assert metrics["execute_count"] == 2
        assert metrics["last_patient_count"] == 1
        assert metrics["prepared_count"] >= 1

    def test_evaluate_with_inline_library_resource(self, conn):
        """In-memory Measure/Library resources should avoid filesystem bridges."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({
            "resourceType": "Patient",
            "id": "p1",
            "gender": "female",
            "birthDate": "1990-01-01",
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "inline-measure",
            "library": ["http://example.com/Library/InlineMeasure"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        cql_text = '''library InlineMeasure
using FHIR version '4.0.1'
context Patient
define "Initial Population":
    Patient.gender = 'female'
'''
        library_resource = {
            "resourceType": "Library",
            "id": "InlineMeasure",
            "name": "InlineMeasure",
            "url": "http://example.com/Library/InlineMeasure",
            "content": [{
                "contentType": "text/cql",
                "data": base64.b64encode(cql_text.encode()).decode(),
            }],
        }

        evaluator = MeasureEvaluator(conn)
        result = evaluator.evaluate(
            measure_ref=measure_json,
            cql_library_path=library_resource,
            artifact_resolver=FileArtifactResolver(),
        )

        assert bool(result.dataframe.loc[0, "initial_population"]) is True

    def test_file_resolver_uses_primary_library_directory_for_includes(
        self, conn, tmp_path
    ):
        """Path callers should resolve sibling CQL includes through the resolver."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({
            "resourceType": "Patient",
            "id": "p1",
            "gender": "male",
            "birthDate": "1990-01-01",
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "include-measure",
            "library": ["http://example.com/Library/IncludeMeasure"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        main_cql = tmp_path / "IncludeMeasure.cql"
        main_cql.write_text('''library IncludeMeasure
using FHIR version '4.0.1'
include HelperLibrary called Helper
context Patient
define "Initial Population":
    Helper."Is Male"
''')
        helper_cql = tmp_path / "HelperLibrary.cql"
        helper_cql.write_text('''library HelperLibrary
using FHIR version '4.0.1'
context Patient
define "Is Male":
    Patient.gender = 'male'
''')

        evaluator = MeasureEvaluator(conn)
        result = evaluator.evaluate(
            measure_bundle=measure_json,
            cql_library_path=main_cql,
        )

        assert bool(result.dataframe.loc[0, "initial_population"]) is True

    def test_compiled_measure_omits_patient_columns_without_implicit_patient_access(
        self, conn, tmp_path
    ):
        """CQL without implicit Patient access should keep _patients lean."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
        loader.load_resource({
            "resourceType": "Encounter",
            "id": "e1",
            "subject": {"reference": "Patient/p1"},
            "status": "finished",
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "compiled-no-demographics",
            "library": ["http://example.com/Library/CompiledNoDemographics"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        cql_path = tmp_path / "compiled_no_demographics.cql"
        cql_path.write_text('''library CompiledNoDemographics
using FHIR version '4.0.1'
context Patient
define "Finished Encounters":
    [Encounter] E where E.status = 'finished'
define "Initial Population":
    exists "Finished Encounters"
''')

        evaluator = MeasureEvaluator(conn)
        compiled = evaluator.compile_measure(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
            patient_scope="target_table",
        )
        sql = compiled.groups[0].sql
        assert "_patient_demographics" not in sql
        assert "patient_resource" not in sql
        assert "birth_date" not in sql

        result = evaluator.execute_compiled_measure(compiled, patient_ids=["p1"])
        assert bool(result.dataframe.loc[0, "initial_population"]) is True

    def test_compiled_target_table_handles_forward_set_operation_sources(
        self, conn, tmp_path
    ):
        """Set-operation query sources should not keep scalar patient correlation."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
        loader.load_resource({
            "resourceType": "Encounter",
            "id": "e1",
            "subject": {"reference": "Patient/p1"},
            "status": "finished",
            "class": {"code": "IMP"},
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "compiled-forward-set-op",
            "library": ["http://example.com/Library/CompiledForwardSetOp"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        cql_path = tmp_path / "compiled_forward_set_op.cql"
        cql_path.write_text('''library CompiledForwardSetOp
using FHIR version '4.0.1'
context Patient
define "Finished Encounters":
    [Encounter] E where E.status = 'finished'
define "Intersected Encounters":
    ("Finished Encounters" intersect "Inpatient Encounters") Encounter
        where Encounter.status = 'finished'
define "Inpatient Encounters":
    [Encounter] E where E.class.code = 'IMP'
define "Initial Population":
    exists "Intersected Encounters"
''')

        evaluator = MeasureEvaluator(conn)
        compiled = evaluator.compile_measure(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
            patient_scope="target_table",
        )

        sql = compiled.groups[0].sql
        assert "WHERE sub.patient_id = Encounter.patient_id" not in sql

        result = evaluator.execute_compiled_measure(compiled, patient_ids=["p1"])
        assert bool(result.dataframe.loc[0, "initial_population"]) is True

    def test_compiled_target_table_preserves_scalar_multi_source_returns(
        self, conn, tmp_path
    ):
        """Computed multi-source returns should materialize scalar value columns."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
        loader.load_resource({
            "resourceType": "Encounter",
            "id": "e1",
            "subject": {"reference": "Patient/p1"},
            "status": "finished",
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "compiled-scalar-multi-source",
            "library": ["http://example.com/Library/CompiledScalarMultiSource"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        cql_path = tmp_path / "compiled_scalar_multi_source.cql"
        cql_path.write_text('''library CompiledScalarMultiSource
using FHIR version '4.0.1'
context Patient
define "Encounter Statuses":
    [Encounter] E return E.status
define "Matching Statuses":
    from
        "Encounter Statuses" Status1,
        "Encounter Statuses" Status2
        where Status1 = Status2
        return ToString(Status1)
define "Initial Population":
    exists "Matching Statuses"
''')

        evaluator = MeasureEvaluator(conn)
        compiled = evaluator.compile_measure(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
            patient_scope="target_table",
        )

        sql = compiled.groups[0].sql
        assert '"Matching Statuses" AS (\nSELECT Status1.patient_id' in sql
        assert 'AS value FROM "Encounter Statuses" AS Status1' in sql
        assert 'SELECT sub.resource FROM "Matching Statuses"' not in sql

        result = evaluator.execute_compiled_measure(compiled, patient_ids=["p1"])
        assert bool(result.dataframe.loc[0, "initial_population"]) is True

    def test_compiled_target_table_preserves_scalar_multi_source_let_returns(
        self, conn, tmp_path
    ):
        """Multi-source returns through let aliases should materialize value columns."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
        loader.load_resource({
            "resourceType": "Observation",
            "id": "o1",
            "subject": {"reference": "Patient/p1"},
            "status": "final",
            "valueInteger": 5,
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "compiled-scalar-multi-source-let",
            "library": ["http://example.com/Library/CompiledScalarMultiSourceLet"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        cql_path = tmp_path / "compiled_scalar_multi_source_let.cql"
        cql_path.write_text('''library CompiledScalarMultiSourceLet
using FHIR version '4.0.1'
context Patient
define "Score Differences":
    from
        [Observation] FirstScore,
        [Observation] FollowUpScore
        let Change: (FirstScore.value as Integer) - (FollowUpScore.value as Integer)
        return Change
define "Initial Population":
    exists ("Score Differences" Score where Score >= 0)
''')

        evaluator = MeasureEvaluator(conn)
        compiled = evaluator.compile_measure(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
            patient_scope="target_table",
        )

        sql = compiled.groups[0].sql
        assert '"Score Differences" AS (\nSELECT FirstScore.patient_id' in sql
        assert 'AS value FROM "Observation" AS FirstScore' in sql
        assert "Score.value" in sql

        result = evaluator.execute_compiled_measure(compiled, patient_ids=["p1"])
        assert bool(result.dataframe.loc[0, "initial_population"]) is True

    def test_compiled_target_table_preserves_resource_tuple_field_returns(
        self, conn, tmp_path
    ):
        """Tuple fields containing resources should stay resource-backed."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
        loader.load_resource({
            "resourceType": "Encounter",
            "id": "e1",
            "subject": {"reference": "Patient/p1"},
            "status": "finished",
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "compiled-resource-tuple-field",
            "library": ["http://example.com/Library/CompiledResourceTupleField"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        cql_path = tmp_path / "compiled_resource_tuple_field.cql"
        cql_path.write_text('''library CompiledResourceTupleField
using FHIR version '4.0.1'
context Patient
define "Encounter Tuples":
    [Encounter] E
        return Tuple { encounter: E, marker: 'kept' }
define "Returned Encounters":
    "Encounter Tuples" T
        return T.encounter
define "Initial Population":
    exists ("Returned Encounters" E where E.status = 'finished')
''')

        evaluator = MeasureEvaluator(conn)
        compiled = evaluator.compile_measure(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
            patient_scope="target_table",
        )

        sql = compiled.groups[0].sql
        assert '"Returned Encounters" AS (' in sql
        assert "_inner._resource_data AS resource" in sql
        assert 'FROM "Encounter Tuples" AS T' in sql
        assert "E.resource" in sql

        result = evaluator.execute_compiled_measure(compiled, patient_ids=["p1"])
        assert bool(result.dataframe.loc[0, "initial_population"]) is True

    def test_compiled_target_table_traces_forward_resource_query_columns(
        self, conn, tmp_path
    ):
        """Forward resource-returning query references should use resource columns."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
        loader.load_resource({
            "resourceType": "Encounter",
            "id": "e1",
            "subject": {"reference": "Patient/p1"},
            "status": "finished",
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "compiled-forward-resource-query",
            "library": ["http://example.com/Library/CompiledForwardResourceQuery"],
            "group": [{
                "population": [{
                    "code": {"coding": [{"code": "initial-population"}]},
                    "criteria": {"expression": "Initial Population"},
                }]
            }],
        }
        cql_path = tmp_path / "compiled_forward_resource_query.cql"
        cql_path.write_text('''library CompiledForwardResourceQuery
using FHIR version '4.0.1'
context Patient
define "Initial Population":
    "Forward Returned Encounters".id contains 'e1'
define "Forward Returned Encounters":
    from
        [Encounter] Encounter1,
        [Encounter] Encounter2
        where Encounter1.status = Encounter2.status
        return Encounter1
''')

        evaluator = MeasureEvaluator(conn)
        compiled = evaluator.compile_measure(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
            patient_scope="target_table",
        )

        sql = compiled.groups[0].sql
        assert 'SELECT sub.resource FROM "Forward Returned Encounters"' in sql
        assert 'SELECT sub.value FROM "Forward Returned Encounters"' not in sql

        result = evaluator.execute_compiled_measure(compiled, patient_ids=["p1"])
        assert bool(result.dataframe.loc[0, "initial_population"]) is True

    def test_evaluate_simple_stratified_measure(self, conn, tmp_path):
        """Stratifier expressions should flow through evaluation and reporting."""
        from fhir4ds.cql import FHIRDataLoader
        loader = FHIRDataLoader(conn)
        loader.load_resource({
            "resourceType": "Patient",
            "id": "p1",
            "gender": "male",
            "birthDate": "1990-01-01",
        })
        loader.load_resource({
            "resourceType": "Patient",
            "id": "p2",
            "gender": "female",
            "birthDate": "1990-01-01",
        })

        measure_json = {
            "resourceType": "Measure",
            "id": "test-stratified",
            "library": ["http://example.com/Library/TestStratified"],
            "group": [{
                "population": [
                    {
                        "code": {"coding": [{"code": "initial-population"}]},
                        "criteria": {"expression": "Initial Population"},
                    },
                    {
                        "code": {"coding": [{"code": "denominator"}]},
                        "criteria": {"expression": "Denominator"},
                    },
                    {
                        "code": {"coding": [{"code": "numerator"}]},
                        "criteria": {"expression": "Numerator"},
                    },
                ],
                "stratifier": [{
                    "id": "payer-line",
                    "code": {"text": "Payer Line"},
                    "criteria": {"expression": "Payer Line"},
                }],
            }],
        }
        cql_text = '''library TestStratified
using FHIR version '4.0.1'
context Patient
define "Initial Population":
    true
define "Denominator":
    true
define "Numerator":
    Patient.gender = 'male'
define "Payer Line":
    if Patient.gender = 'male' then 'Medicare' else 'Medicaid'
'''
        cql_path = tmp_path / "test_stratified.cql"
        cql_path.write_text(cql_text)

        evaluator = MeasureEvaluator(conn)
        result = evaluator.evaluate(
            measure_bundle=measure_json,
            cql_library_path=str(cql_path),
        )
        assert "stratifier_1" in result.dataframe.columns

        summary = evaluator.summary_report(result)
        strata = {
            stratum["text"]: stratum["population"]
            for stratum in summary["stratifiers"][0]["strata"]
        }
        assert strata["Medicare"]["initial-population"] == 1
        assert strata["Medicaid"]["initial-population"] == 1
        assert sum(
            counts["initial-population"] for counts in strata.values()
        ) == summary["initial_population"]

        report = evaluator.to_measure_report(
            result, period_start="2026-01-01", period_end="2026-12-31"
        )
        assert report["group"][0]["stratifier"][0]["id"] == "payer-line"

    def test_generate_narratives_true_requires_audit(self, conn):
        evaluator = MeasureEvaluator(conn)
        with pytest.raises(ValueError, match="Narratives require audit=True"):
            evaluator.evaluate(
                measure_bundle={"resourceType": "Measure", "id": "t", "group": [{"population": [{"code": {"coding": [{"code": "initial-population"}]}, "criteria": {"expression": "IP"}}]}]},
                cql_library_path="/nonexistent.cql",
                audit=False,
                generate_narratives=True,
            )


@pytest.mark.skipif(
    not (DQM_2026 / "resources" / "measure" / "Measure-SupportingEvidenceExample.json").exists(),
    reason="Benchmarking fixtures not available",
)
class TestMeasureEvaluatorSupportingEvidence:
    """Test with real SupportingEvidenceExample measure."""

    def test_parse_and_extract(self):
        """Verify parser can extract populations from real measure."""
        measure = json.loads(
            (DQM_2026 / "resources" / "measure" / "Measure-SupportingEvidenceExample.json").read_text()
        )
        parser = MeasureParser()
        pop_map = parser.parse(measure)
        assert pop_map.measure_id == "SupportingEvidenceExample"
        assert len(pop_map.groups) == 1
        assert len(pop_map.groups[0].populations) >= 4


class TestMeasureEvaluatorSummaryReport:
    def test_summary_report_with_audit_structs(self):
        """Test summary_report handles struct-typed columns."""
        import pandas as pd

        df = pd.DataFrame(
            {
                "patient_id": ["P1", "P2", "P3"],
                "initial_population": [
                    {"result": True, "evidence": []},
                    {"result": True, "evidence": []},
                    {"result": False, "evidence": []},
                ],
                "denominator": [
                    {"result": True, "evidence": []},
                    {"result": True, "evidence": []},
                    {"result": False, "evidence": []},
                ],
                "numerator": [
                    {"result": True, "evidence": [{"resource_id": "Obs/1"}]},
                    {"result": False, "evidence": [{"resource_id": "Obs/2"}]},
                    {"result": False, "evidence": []},
                ],
            }
        )
        evaluator = MeasureEvaluator(conn=None)
        summary = evaluator.summary_report(df)
        assert summary["initial_population"] == 2
        assert summary["denominator"] == 2
        assert summary["numerator"] == 1
        assert summary["total_patients"] == 3
