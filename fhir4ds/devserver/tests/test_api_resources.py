"""v3 Slice 1 API integration tests: header/parameters/valuesets/patients routes."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
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
    "parameter \"MinAge\" Integer default 18\n\n"
    "// # %% [name: IsMale]\n"
    "define IsMale: Patient.gender = 'male'\n"
)

VS = {
    "resourceType": "ValueSet",
    "id": "vs1",
    "url": "http://example.com/vs1",
    "compose": {
        "include": [
            {"system": "http://loinc.org", "concept": [{"code": "8480-6", "display": "BP"}]}
        ]
    },
}

PORT = 18871


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("ws")
    (tmp_path / "cql").mkdir()
    (tmp_path / "cql" / "Demographics.cql").write_text(CQL)
    (tmp_path / "valuesets").mkdir()
    (tmp_path / "valuesets" / "vs1.json").write_text(json.dumps(VS))
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
    yield srv, tmp_path
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


class TestLibraryHeader:
    def test_header_shape(self, server):
        h = call("/api/library-header?library=Demographics")
        assert h["library"] == "Demographics"
        assert [(p["name"], p["type"], p["default"]) for p in h["parameters"]] == [
            ("MinAge", "Integer", "18")
        ]

    def test_unknown_library_envelope(self, server):
        d = call("/api/library-header?library=Nope")
        assert d["ok"] is False
        assert "unknown library" in d["diagnostics"][0]["message"]


class TestPatients:
    def test_patients_sorted(self, server):
        assert call("/api/patients")["patients"] == ["p1", "p2"]


class TestParametersRoute:
    def test_upsert_round_trip_with_text_threading(self, server):
        r1 = call(
            "/api/parameters",
            {"library": "Demographics", "action": "upsert", "name": "Gender", "type": "String"},
        )
        assert 'parameter "Gender" String' in r1["text"]
        r2 = call(
            "/api/parameters",
            {
                "library": "Demographics",
                "action": "upsert",
                "name": "MinAge",
                "type": "Integer",
                "default": "21",
                "text": r1["text"],
            },
        )
        assert 'parameter "MinAge" Integer default 21' in r2["text"]
        r3 = call(
            "/api/parameters",
            {"library": "Demographics", "action": "delete", "name": "Gender", "text": r2["text"]},
        )
        assert 'parameter "Gender"' not in r3["text"]
        assert [(p["name"], p["default"]) for p in r3["parameters"]] == [("MinAge", "21")]

    def test_file_untouched_without_text(self, server):
        call(
            "/api/parameters",
            {"library": "Demographics", "action": "upsert", "name": "Later", "type": "String"},
        )
        disk = (server[1] / "cql" / "Demographics.cql").read_text()
        assert 'parameter "Later"' not in disk


class TestValueSetRoute:
    def test_read_shape(self, server):
        d = call(f"/api/valueset?path={server[1] / 'valuesets' / 'vs1.json'}")
        assert d["concepts"] == [
            {"system": "http://loinc.org", "code": "8480-6", "display": "BP"}
        ]
        assert d["used_by"] == []
        assert d["stale"] is False

    def test_edit_add_sets_stale_and_writes_file(self, server):
        d = call(
            "/api/valueset/edit",
            {
                "path": str(server[1] / "valuesets" / "vs1.json"),
                "edit": {"action": "add", "system": "http://loinc.org", "code": "8462-4"},
            },
        )
        assert len(d["concepts"]) == 2
        assert d["stale"] is True
        assert call("/health")["valuesets_stale"] is True
        disk = json.loads((server[1] / "valuesets" / "vs1.json").read_text())
        assert [c["code"] for c in disk["compose"]["include"][0]["concept"]] == ["8480-6", "8462-4"]

    def test_edit_invalid_system_rejected(self, server):
        d = call(
            "/api/valueset/edit",
            {
                "path": str(server[1] / "valuesets" / "vs1.json"),
                "edit": {"action": "add", "system": "not-a-uri", "code": "x"},
            },
        )
        assert d["ok"] is False
        assert "absolute http(s) URI" in d["diagnostics"][0]["message"]

    def test_restart_clears_stale(self, server):
        call("/api/kernel/restart", {})
        assert call("/health")["valuesets_stale"] is False


class TestUnknownPaths:
    def test_valueset_path_outside_workspace_rejected(self, server):
        d = call("/api/valueset?path=/etc/passwd")
        assert d["ok"] is False
