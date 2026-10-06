"""API tests for ViewDefinition routes (v3 slice 4)."""

import json
import threading
import time
from pathlib import Path

import pytest
import urllib.request

from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import Watcher, EventBus
from fhir4ds.devserver.api import create_server

PORT = 18895

CQL = """library Demographics version '1.0.0'
using FHIR version '4.0.1'

context Patient

// # %% [name: IsMale]
define IsMale: Patient.gender = 'male'
"""

VD = {
    "resource": "Patient",
    "name": "PxDemo",
    "select": [
        {
            "column": [
                {"name": "id", "path": "id"},
                {"name": "gender", "path": "gender"},
                {"name": "given", "path": "name.given", "collection": True},
            ]
        }
    ],
}

BAD_VD = {
    "resource": "Patient",
    "name": "BadDemo",
    "select": [
        {"column": [{"name": "id", "path": "id", "nam": "oops"}]}
    ],
}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    ws = tmp_path_factory.mktemp("ws")
    (ws / "cql").mkdir()
    (ws / "views").mkdir()
    (ws / "valuesets").mkdir()
    (ws / "data").mkdir()
    (ws / "cql" / "Demographics.cql").write_text(CQL)
    (ws / "views" / "pxdemo.json").write_text(json.dumps(VD, indent=2))
    (ws / "views" / "bad.json").write_text(json.dumps(BAD_VD, indent=2))
    patients = []
    for i in range(1, 7):
        gender = "male" if i % 2 else "female"
        pat = {
            "resourceType": "Patient",
            "id": f"p{i}",
            "gender": gender,
            "birthDate": "1974-12-25" if i % 2 else "1990-01-01",
        }
        if i % 2:
            pat["name"] = [{"given": ["John", "Kim"], "family": "Doe"}]
        patients.append(json.dumps(pat))
    (ws / "data" / "patients.ndjson").write_text("\n".join(patients) + "\n")
    cfg = load_config(str(ws))
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    watcher = Watcher(cfg, EventBus())
    srv = create_server(mgr, watcher, port=PORT)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    yield srv, ws
    srv.shutdown()


def call(server, path, body=None):
    if body is None:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}")
    else:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


class TestViewRead:
    def test_read_happy(self, server):
        srv, ws = server
        path = str(ws / "views" / "pxdemo.json")
        d = call(server, f"/api/view?path={urllib.request.quote(path)}")
        assert d["ok"] is True
        assert d["resource"] == "Patient"
        assert d["name"] == "PxDemo"
        assert '"id"' in d["text"]

    def test_unknown_path(self, server):
        d = call(server, "/api/view?path=/etc/passwd")
        assert d["ok"] is False


class TestViewRun:
    def test_run_happy_by_path(self, server):
        srv, ws = server
        path = str(ws / "views" / "pxdemo.json")
        d = call(server, "/api/view/run", {"path": path})
        assert d["ok"] is True
        assert d["columns"] == ["id", "gender", "given"]
        assert d["resource_count"] == 6
        rows_by_id = {r["id"]: r for r in d["rows"]}
        assert rows_by_id["p1"]["gender"] == "male"
        assert rows_by_id["p1"]["given"] == ["John", "Kim"]
        assert rows_by_id["p2"]["given"] == []
        assert "SELECT" in d["sql"]

    def test_invariant_error_inline(self, server):
        srv, ws = server
        path = str(ws / "views" / "bad.json")
        d = call(server, "/api/view/run", {"path": path})
        assert d["ok"] is False
        assert "Unsupported column field(s)" in d["diagnostics"][0]["message"]
        assert "'nam'" in d["diagnostics"][0]["message"]

    def test_invalid_json(self, server):
        d = call(server, "/api/view/run", {"text": "{not json"})
        assert d["ok"] is False
        assert "invalid JSON" in d["diagnostics"][0]["message"]

    def test_non_object(self, server):
        d = call(server, "/api/view/run", {"text": "[1, 2]"})
        assert d["ok"] is False
        assert "JSON object" in d["diagnostics"][0]["message"]

    def test_missing_resource(self, server):
        d = call(server, "/api/view/run", {"text": json.dumps({"name": "X"})})
        assert d["ok"] is False
        assert "resource" in d["diagnostics"][0]["message"]

    def test_inline_text_override(self, server):
        d = call(server, "/api/view/run", {"text": json.dumps(VD)})
        assert d["ok"] is True
        assert d["columns"] == ["id", "gender", "given"]

    def test_unknown_run_path(self, server):
        d = call(server, "/api/view/run", {"path": "/nope/missing.json"})
        assert d["ok"] is False
