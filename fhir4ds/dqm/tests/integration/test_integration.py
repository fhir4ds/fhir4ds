"""End-to-end integration tests for MeasureEvaluator with DuckDB."""

import json
from pathlib import Path

import duckdb
import pytest

from fhir4ds.dqm import MeasureEvaluator, MeasureParser

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
