"""End-to-end integration tests for MeasureEvaluator with DuckDB."""

import json
import pytest
import duckdb
import pandas as pd
from pathlib import Path

from ..import MeasureEvaluator, MeasureParser
from ..errors import DQMError


BENCHMARKING_DIR = Path(__file__).resolve().parent.parent.parent.parent / "benchmarking"
DQM_2026 = BENCHMARKING_DIR / "dqm-content-qicore-2026" / "input"
ECQ_2025 = BENCHMARKING_DIR / "ecqm-content-qicore-2025"


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
