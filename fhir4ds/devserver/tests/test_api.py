"""API integration tests: HTTP routes over a live server (urllib client)."""

from __future__ import annotations

import json
import threading
import time
import urllib.request

import pytest

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import EventBus, Watcher

CQL = (
    "library Demographics version '1.0.0'\n"
    "using FHIR version '4.0.1'\n\n"
    "define \"Male\": Patient.gender = 'male'\n"
)

PORT = 18801


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("ws")
    (tmp_path / "cql").mkdir()
    (tmp_path / "cql" / "Demographics.cql").write_text(CQL)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "patients.ndjson").write_text(
        '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n'
        '{"resourceType": "Patient", "id": "p2", "gender": "female"}\n'
    )
    cfg = load_config(tmp_path)
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    w = Watcher(cfg, EventBus())
    srv = create_server(mgr, w, port=PORT)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    yield srv
    srv.shutdown()


def call(path, body=None):
    if body is None:
        r = urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=30)
    else:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        r = urllib.request.urlopen(req, timeout=60)
    return json.loads(r.read())


class TestHealth:
    def test_health_shape(self, server):
        h = call("/health")
        assert h["ok"] and h["status"] == "ok"
        assert h["kernel_id"].startswith("kernel-")
        assert isinstance(h["watching"], int)


class TestWorkspace:
    def test_workspace_lists_library(self, server):
        w = call("/api/workspace")
        names = [l["name"] for l in w["workspace"]["libraries"]]
        assert "Demographics" in names

    def test_library_detail(self, server):
        d = call("/api/libraries/Demographics")
        assert d["parse_ok"] and "Male" in d["definitions"]

    def test_library_not_found_envelope(self, server):
        d = call("/api/libraries/Nope")
        assert not d["ok"]
        assert d["diagnostics"][0]["code"] == "NOT_FOUND"


class TestEvaluate:
    def test_full_library(self, server):
        r = call("/api/evaluate", {"library": "Demographics"})
        assert r["ok"]
        by_patient = {row["patient_id"]: row for row in r["rows"]}
        assert by_patient["p1"]["Male"] is True
        assert by_patient["p2"]["Male"] is False

    def test_per_define_narrowing(self, server):
        """Per-define v1: output_columns={define: define} projection.

        evaluate_library returns every definition column; narrowing
        output_columns projects the SQL to the single define — same
        engine seam, no new capability.
        """
        r = call("/api/evaluate", {"library": "Demographics", "define": "Male"})
        assert r["ok"]
        assert r["columns"] == ["patient_id", "Male"]

    def test_inline_libraries_apply_loop(self, server):
        """Edit loop: inline LibraryText via Apply — zero server writes."""
        text = CQL + 'define "Extra": true\n'
        r = call("/api/evaluate", {"libraries": [{"name": "Demographics", "text": text}]})
        assert r["ok"]
        assert "Extra" in r["columns"]

    def test_missing_library_flagged(self, server):
        r = call("/api/evaluate", {"library": "Ghost"})
        assert not r["ok"]
        assert r["diagnostics"][0]["code"] == "NOT_FOUND"


class TestTranslateVerifyExplain:
    def test_translate_emits_sql(self, server):
        r = call("/api/translate", {"library": "Demographics"})
        assert r["ok"] and len(r["sql"]) > 0
        assert "Male" in r["definitions"]

    def test_verify_cases(self, server):
        r = call(
            "/api/verify",
            {
                "library": "Demographics",
                "cases": [
                    {"patient": "p1", "expect": True, "define": "Male"},
                    {"patient": "p2", "expect": False, "define": "Male"},
                ],
            },
        )
        assert r["ok"] and r["passed"] is True  # bool: all cases passed
        assert r["summary"]["Male"] == 1

    def test_explain_evidence(self, server):
        r = call("/api/explain", {"library": "Demographics", "patient_id": "p1"})
        assert r["ok"] and r.get("patient_id") == "p1"

    def test_fhirpath_eval(self, server):
        import urllib.parse

        resource = urllib.parse.quote('{"id": "abc"}')
        r = call(f"/api/fhirpath?expr=id&resource={resource}")
        assert r["ok"]


class TestKernelRestart:
    def test_restart_swaps_kernel_and_drains(self, server):
        """Conductor note: old conn completes in-flight work; new calls
        get the new kernel."""
        old_id = call("/health")["kernel_id"]
        old_kernel = server.kernel_manager.current()
        results = {}

        def in_flight():
            conn = old_kernel.conn  # holder keeps the old connection alive
            time.sleep(0.2)
            try:
                conn.execute("SELECT 1").fetchone()
                results["drained"] = True
            except Exception as exc:  # pragma: no cover
                results["drained"] = repr(exc)

        t = threading.Thread(target=in_flight)
        t.start()
        r = call("/api/kernel/restart", {})
        t.join()
        assert r["status"] == "restarted"
        assert r["kernel_id"] != old_id
        assert results.get("drained") is True
        # new requests hit the new kernel
        assert call("/health")["kernel_id"] == r["kernel_id"]
        # and evaluation still works after restart
        assert call("/api/evaluate", {"library": "Demographics"})["ok"]
