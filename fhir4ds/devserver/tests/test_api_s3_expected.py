"""S3 (c-cleanroom-ux5 item 3): expected-results store + test-run APIs."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.expected_store import (
    build_expected_report,
    delete_expected_report,
    is_test_case_report,
    load_expected_reports,
    parse_expected_groups,
    patient_from_report,
    save_expected_report,
)
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import EventBus, Watcher

try:
    import tomllib
except ImportError:
    import tomli as tomllib

CQL = """library S3Measure
define "Initial Population": Patient.gender = 'male'
"""

MEASURE = {
    "resourceType": "Measure",
    "name": "S3M",
    "status": "active",
    "library": ["urn:s3m"],
    "group": [
        {
            "id": "g1",
            "population": [
                {"code": {"coding": [{"code": "initial-population"}]},
                 "criteria": {"language": "text/cql", "expression": "Initial Population"}},
            ],
        }
    ],
}

NDJSON = (
    '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n'
    '{"resourceType": "Patient", "id": "p2", "gender": "female"}\n'
)

PORT = 18881


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("ws_s3")
    (tmp_path / "cql").mkdir()
    (tmp_path / "cql" / "S3Measure.cql").write_text(CQL)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "patients.ndjson").write_text(NDJSON)
    cfg = load_config(tmp_path)
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    w = Watcher(cfg, EventBus())
    srv = create_server(mgr, w, port=PORT)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    yield srv, tmp_path
    srv.shutdown()


def call(path, body=None):
    if body is None:
        r = urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=60)
    else:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        r = urllib.request.urlopen(req, timeout=120)
    return json.loads(r.read())


class TestExpectedStore:
    def test_build_and_roundtrip(self, tmp_path):
        report = build_expected_report(
            "p1", [{"id": "g1", "population": [{"code": "initial-population", "count": 1}]}],
            period_start="2026-01-01", period_end="2026-12-31",
        )
        assert is_test_case_report(report)
        assert patient_from_report(report) == "p1"
        groups = parse_expected_groups(report)
        assert groups[0]["population"][0]["code"] == "initial-population"
        target = save_expected_report(tmp_path, "M1", report)
        assert target.name == "p1.json"
        loaded = load_expected_reports(tmp_path, "M1")
        assert len(loaded) == 1 and patient_from_report(loaded[0]) == "p1"

    def test_madie_shape_parsed(self, tmp_path):
        # MADiE: population code under code.coding[0].code + display ids
        madie = {
            "resourceType": "MeasureReport",
            "subject": {"reference": "Patient/p9"},
            "meta": {"profile": ["http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-test-cases"]},
            "group": [{"id": "group-1", "population": [
                {"id": "initial-population-1", "code": {"coding": [{"code": "initial-population"}]}, "count": 1},
            ]}],
        }
        assert is_test_case_report(madie)
        groups = parse_expected_groups(madie)
        assert groups[0]["population"][0] == {
            "code": "initial-population", "count": 1, "display_id": "initial-population-1"}
        save_expected_report(tmp_path, "MADiE", madie)
        assert len(load_expected_reports(tmp_path, "MADiE")) == 1

    def test_delete_and_bad_names(self, tmp_path):
        report = build_expected_report("p2", [])
        save_expected_report(tmp_path, "M1", report)
        assert delete_expected_report(tmp_path, "M1", "p2") is True
        assert delete_expected_report(tmp_path, "M1", "p2") is False
        with pytest.raises(ValueError):
            save_expected_report(tmp_path, "../evil", report)
        with pytest.raises(ValueError):
            save_expected_report(tmp_path, "M1", {"resourceType": "MeasureReport"})


class TestCaptureRunCycle:
    def test_capture_save_run_diff(self, server):
        _, tmp = server
        # 1. capture: seeds expected reports from ACTUAL (p1 male → 1, p2 → 0)
        cap = call("/api/tests/capture", {
            "library": "S3Measure", "measure": MEASURE, "measure_name": "S3M",
        })
        assert cap["ok"], cap
        assert len(cap["reports"]) == 2
        byp = {patient_from_report(r): r for r in cap["reports"]}
        assert byp["p1"]["group"][0]["population"][0]["count"] == 1
        assert byp["p2"]["group"][0]["population"][0]["count"] == 0

        # 2. save expectations unchanged
        sv = call("/api/tests/expected/save", {"measure": "S3M", "reports": cap["reports"]})
        assert sv["ok"] and sv["count"] == 2

        # 3. run: actual == expected → all pass
        run = call("/api/tests/run", {
            "library": "S3Measure", "measure": MEASURE, "measure_name": "S3M",
        })
        assert run["ok"] and run["failed"] == 0 and run["passed"] == 2

        # 4. edit expectation: flip p2 to 1 → mismatch surfaces
        edited = [dict(r) for r in cap["reports"]]
        for r in edited:
            if patient_from_report(r) == "p2":
                r["group"] = [{"id": "g1", "population": [
                    {"code": "initial-population", "count": 1}]}]
        call("/api/tests/expected/save", {"measure": "S3M", "reports": edited})
        run2 = call("/api/tests/run", {
            "library": "S3Measure", "measure": MEASURE, "measure_name": "S3M",
        })
        assert run2["ok"] is False and run2["failed"] == 1
        bad = [r for r in run2["rows"] if not r["pass"]]
        assert bad[0]["patient"] == "p2"
        assert bad[0]["expected"] == 1 and bad[0]["actual"] == 0

        # 5. GET lists stored patients
        got = call("/api/tests/expected?measure=S3M")
        assert got["count"] == 2

        # 6. delete one patient expectation
        dl = call("/api/tests/expected/delete", {"measure": "S3M", "patient": "p2"})
        assert dl["ok"] and dl["removed"] is True

    def test_files_land_in_measures_expected_patients(self, server):
        _, tmp = server
        expected_dir = tmp / "measures" / "expected" / "patients" / "S3M"
        assert expected_dir.is_dir()
        assert (expected_dir / "p1.json").is_file()
