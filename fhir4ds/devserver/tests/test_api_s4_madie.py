"""S4 (c-cleanroom-ux5 item 4): MADiE package + test-case ZIP importers."""

from __future__ import annotations

import base64
import io
import json
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import pytest

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.expected_store import (
    load_expected_reports,
    patient_from_report,
    parse_expected_groups,
)
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.madie_import import (
    import_package_zip,
    import_tests_zip,
    is_expected_measure_report,
)
from fhir4ds.devserver.watcher import EventBus, Watcher

PORT = 18885

IS_TEST_CASES_EXT = {
    "url": "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-isTestCases",
    "valueBoolean": True,
}


class _FakeServer:
    """Minimal server double carrying watcher._cfg + published events."""

    def __init__(self, root: Path):
        cfg = load_config(root)
        self.watcher = Watcher(cfg, EventBus())
        self.published: list[list[str]] = []
        self.watcher.publish_changed = lambda paths: self.published.append(paths)  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Synthetic MADiE-shaped zips (built from the §0 source reading)
# ---------------------------------------------------------------------------


def build_package_zip() -> bytes:
    measure = {
        "resourceType": "Measure",
        "id": "180",
        "name": "TestMeasure",
        "status": "active",
        "library": ["http://example.org/lib"],
        "group": [
            {
                "id": "g1",
                "population": [
                    {
                        "code": {"coding": [{"code": "initial-population"}]},
                        "criteria": {
                            "language": "text/cql-identifier",
                            "expression": "Initial Population",
                        },
                    }
                ],
            }
        ],
    }
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {"resource": measure},
            {
                "resource": {
                    "resourceType": "ValueSet",
                    "id": "test-vs",
                    "url": "http://example.org/vs/test-vs",
                    "compose": {
                        "include": [{"system": "http://example.org/sys"}]
                    },
                }
            },
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("TestMeasure-v1.0.0-FHIR.json", json.dumps(bundle))
        zf.writestr("TestMeasure-v1.0.0-FHIR.xml", "<ignored/>")
        zf.writestr("TestMeasure-v1.0.0-FHIR.html", "<html>ignored</html>")
        zf.writestr("cql/TestLibrary-1.0.0.cql", "library TestLibrary\ndefine \"X\": 1\n")
        zf.writestr(
            "resources/measure-TestMeasure.json", json.dumps(measure)
        )
    return buf.getvalue()


def build_tests_zip(measure_url: str = "http://example.org/TestMeasure|1.0.0") -> bytes:
    def case(pid: str) -> dict:
        return {
            "resourceType": "Bundle",
            "id": f"case-{pid}",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": pid, "gender": "male"}},
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": f"obs-{pid}",
                        "status": "final",
                        "code": {"text": "t"},
                    }
                },
                {
                    "resource": {
                        "resourceType": "MeasureReport",
                        "status": "complete",
                        "type": "individual",
                        "measure": measure_url,
                        "subject": {"reference": f"Patient/{pid}"},
                        "modifierExtension": [IS_TEST_CASES_EXT],
                        "group": [
                            {
                                "id": "g1",
                                "population": [
                                    {
                                        "id": "Initial Population",
                                        "code": {
                                            "coding": [
                                                {"code": "initial-population"}
                                            ]
                                        },
                                        "count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                },
            ],
        }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "patient-1/TestMeasure-v1.0.000-Case1.json", json.dumps(case("patient-1"))
        )
        zf.writestr(
            "patient-2/TestMeasure-v1.0.000-Series1-Case2.json",
            json.dumps(case("patient-2")),
        )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Unit: marker detection
# ---------------------------------------------------------------------------


class TestMarker:
    def test_modifier_extension_form(self):
        mr = {"resourceType": "MeasureReport", "modifierExtension": [IS_TEST_CASES_EXT]}
        assert is_expected_measure_report(mr)

    def test_profile_form(self):
        mr = {
            "resourceType": "MeasureReport",
            "meta": {"profile": ["http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-test-cases"]},
        }
        assert is_expected_measure_report(mr)

    def test_plain_mreport_negative(self):
        assert not is_expected_measure_report({"resourceType": "MeasureReport"})
        assert not is_expected_measure_report({"resourceType": "Patient"})


# ---------------------------------------------------------------------------
# Package import
# ---------------------------------------------------------------------------


class TestPackageImport:
    def test_import_writes_cql_valuesets_measure(self, tmp_path):
        (tmp_path / "cql").mkdir()
        srv = _FakeServer(tmp_path)
        result = import_package_zip(srv, build_package_zip())
        assert result["ok"], result["diagnostics"]
        assert (tmp_path / "cql" / "TestLibrary.cql").read_text().startswith("library TestLibrary")
        vs_files = list((tmp_path / "valuesets").glob("*.json"))
        assert len(vs_files) == 1  # bundle harvest deduped w/ resources/ twin
        measure_files = list((tmp_path / "measures").glob("*.json"))
        assert len(measure_files) == 1
        m = json.loads(measure_files[0].read_text())
        assert m["resourceType"] == "Measure" and m["name"] == "TestMeasure"
        assert srv.published  # changed event fired

    def test_non_zip_rejected(self, tmp_path):
        srv = _FakeServer(tmp_path)
        result = import_package_zip(srv, b"not a zip")
        assert not result["ok"]
        assert "not a valid zip" in result["diagnostics"][0]["message"]

    def test_empty_zip_rejected(self, tmp_path):
        srv = _FakeServer(tmp_path)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass
        result = import_package_zip(srv, buf.getvalue())
        assert not result["ok"]
        assert "no importable content" in result["diagnostics"][0]["message"]

    def test_xml_and_html_skipped(self, tmp_path):
        srv = _FakeServer(tmp_path)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("ignored.xml", "<a/>")
            zf.writestr("ignored.html", "<html/>")
        result = import_package_zip(srv, buf.getvalue())
        assert not result["ok"]


# ---------------------------------------------------------------------------
# Tests import
# ---------------------------------------------------------------------------


class TestTestsImport:
    def test_import_strips_expected_and_writes_cases(self, tmp_path):
        srv = _FakeServer(tmp_path)
        result = import_tests_zip(srv, build_tests_zip(), measure_name="TestMeasure")
        assert result["ok"], result["diagnostics"]
        assert result["counts"] == {"cases": 2, "expected": 2}
        # Patient bundles (trailing MR stripped) under data/<patientId>/
        for pid in ("patient-1", "patient-2"):
            case = tmp_path / "data" / pid / f"TestMeasure-v1.0.000-{('Case1') if pid=='patient-1' else 'Series1-Case2'}.json"
            loaded = json.loads(case.read_text())
            rts = [e["resource"]["resourceType"] for e in loaded["entry"]]
            assert rts == ["Patient", "Observation"]  # MR gone
        # Expected store keyed per patient under measures/expected/patients/
        reports = load_expected_reports(tmp_path / "measures" / "expected", "TestMeasure")
        assert sorted(patient_from_report(r) for r in reports) == ["patient-1", "patient-2"]
        groups = parse_expected_groups(reports[0])
        assert groups[0]["population"][0]["code"] == "initial-population"
        assert groups[0]["population"][0]["count"] == 1

    def test_import_without_expected_marker(self, tmp_path):
        srv = _FakeServer(tmp_path)
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "px"}},
                {"resource": {"resourceType": "MeasureReport",
                              "status": "complete", "type": "individual",
                              "measure": "http://x",
                              "subject": {"reference": "Patient/px"}}},
            ],
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("px/case.json", json.dumps(bundle))
        result = import_tests_zip(srv, buf.getvalue())
        assert result["ok"]
        assert result["counts"]["expected"] == 0
        assert result["counts"]["cases"] == 1
        assert any(d["code"] == "NO_EXPECTATION" for d in result["diagnostics"])
        # Plain MR entry KEPT (not marked -> treated as data, per guard doctrine)
        kept = json.loads((tmp_path / "data" / "px" / "case.json").read_text())
        assert len(kept["entry"]) == 2

    def test_measure_name_defaults_from_mr(self, tmp_path):
        srv = _FakeServer(tmp_path)
        result = import_tests_zip(srv, build_tests_zip("http://example.org/MADiEMeasure|2.0"))
        assert result["ok"]
        # |version suffix stripped from the store key (dir-safe measure name)
        reports = load_expected_reports(tmp_path / "measures" / "expected", "MADiEMeasure")
        assert len(reports) == 2

    def test_not_a_bundle_skipped(self, tmp_path):
        srv = _FakeServer(tmp_path)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("x/readme.json", json.dumps({"hello": 1}))
        result = import_tests_zip(srv, buf.getvalue())
        assert not result["ok"]
        assert "no test-case bundles" in result["diagnostics"][0]["message"]


# ---------------------------------------------------------------------------
# API surface (live server)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("ws_s4")
    (tmp_path / "cql").mkdir()
    cfg = load_config(tmp_path)
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    w = Watcher(cfg, EventBus())
    srv = create_server(mgr, w, port=PORT)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    yield srv, tmp_path
    srv.shutdown()


def call(path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


class TestApiSurface:
    def test_package_roundtrip(self, server):
        _, ws = server
        payload = {"zip_base64": base64.b64encode(build_package_zip()).decode()}
        r = call("/api/madie/import-package", payload)
        assert r["ok"], r["diagnostics"]
        assert r["counts"]["cql"] == 1
        assert (ws / "cql" / "TestLibrary.cql").exists()

    def test_tests_roundtrip(self, server):
        _, ws = server
        payload = {
            "zip_base64": base64.b64encode(build_tests_zip()).decode(),
            "measure_name": "TestMeasure",
        }
        r = call("/api/madie/import-tests", payload)
        assert r["ok"], r["diagnostics"]
        assert r["counts"] == {"cases": 2, "expected": 2}
        assert (ws / "data" / "patient-1").is_dir()

    def test_missing_base64_rejected(self, server):
        r = call("/api/madie/import-package", {})
        assert not r["ok"]
        r = call("/api/madie/import-tests", {"zip_base64": 42})
        assert not r["ok"]

    def test_bad_base64_rejected(self, server):
        r = call("/api/madie/import-package", {"zip_base64": "!!!not-base64!!!"})
        assert not r["ok"]
        assert "invalid base64" in r["diagnostics"][0]["message"]
