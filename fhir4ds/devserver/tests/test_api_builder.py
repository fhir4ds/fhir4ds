"""API tests for the v4.1 Resource Builder routes.

Covers GET /api/schema-tree, POST /api/resource/validate, and
POST /api/resource/save (NDJSON append + data-hint event).
Envelopes follow the devserver doctrine: HTTP 200 for capability
failures with ok=False + diagnostics.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import EventBus, Watcher

PORT = 19005
BASE = f"http://127.0.0.1:{PORT}"

CQL = """library Demographics version '1.0.0'
using FHIR version '4.0.1'

valueset "BPVS": 'http://example.com/bp'

context Patient

// # %% [name: IsMale]
define IsMale: Patient.gender = 'male'
"""

BP_VS = {
    "resourceType": "ValueSet",
    "id": "vs1",
    "url": "http://example.com/bp",
    "compose": {
        "include": [
            {
                "system": "http://loinc.org",
                "concept": [{"code": "8480-6", "display": "BP"}],
            }
        ]
    },
}


def _patient(pid: str, gender: str = "male") -> dict:
    return {
        "resourceType": "Patient",
        "id": pid,
        "gender": gender,
        "birthDate": "1974-12-25",
    }


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    ws = tmp_path_factory.mktemp("builder_ws")
    (ws / "cql").mkdir()
    (ws / "valuesets").mkdir()
    (ws / "data").mkdir()
    (ws / "cql" / "Demographics.cql").write_text(CQL)
    (ws / "valuesets" / "vs1.json").write_text(json.dumps(BP_VS))
    with (ws / "data" / "patients.ndjson").open("w") as fh:
        fh.write(json.dumps(_patient("p1")) + "\n")
        fh.write(json.dumps(_patient("p2", "female")) + "\n")

    cfg = load_config(str(ws))
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    watcher = Watcher(cfg, EventBus())
    srv = create_server(mgr, watcher, port=PORT)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield srv, ws
    srv.shutdown()
    srv.server_close()


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}") as resp:
        return json.loads(resp.read().decode())


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


class TestSchemaTree:
    def test_happy_path(self, server):
        d = _get("/api/schema-tree?resource=Patient&depth=2")
        assert d["ok"] is True
        assert d["resource_type"] == "Patient"
        names = [c["name"] for c in d["root"]["children"]]
        assert "gender" in names and "name" in names
        mo = [c for c in d["root"]["children"] if c["name"] == "managingOrganization"]
        assert mo and mo[0]["reference_targets"] == ["Organization"]

    def test_unknown_resource(self, server):
        d = _get("/api/schema-tree?resource=NotAType")
        assert d["ok"] is False
        assert "NotAType" in d["diagnostics"][0]["message"]

    def test_missing_param(self, server):
        d = _get("/api/schema-tree")
        assert d["ok"] is False

    def test_depth_clamped(self, server):
        d = _get("/api/schema-tree?resource=Patient&depth=99")
        assert d["ok"] is True


class TestResourceValidate:
    def test_valid_patient(self, server):
        d = _post(
            "/api/resource/validate",
            {"resource": _patient("p9", "female")},
        )
        assert d["ok"] is True
        assert d["valid"] is True
        assert d["resource_type"] == "Patient"

    def test_invalid_resource(self, server):
        bad = _patient("")
        d = _post("/api/resource/validate", {"resource": bad})
        assert d["ok"] is True
        assert d["valid"] is False
        assert d["diagnostics"]

    def test_non_object(self, server):
        d = _post("/api/resource/validate", {"resource": "nope"})
        assert d["ok"] is False


class TestResourceSave:
    def test_save_appends_ndjson_and_hints(self, server):
        srv, ws = srv_, ws_ = server
        target = ws / "data" / "patients.ndjson"
        before = target.read_text().splitlines()

        sub = srv.watcher.bus.subscribe()
        try:
            d = _post(
                "/api/resource/save",
                {
                    "resource": _patient("p9", "female"),
                    "dataset_path": str(target),
                },
            )
            assert d["ok"] is True
            assert d["path"] == str(target)
            after = target.read_text().splitlines()
            assert len(after) == len(before) + 1
            assert json.loads(after[-1])["id"] == "p9"

            # data-hint event emitted (never auto-reload doctrine)
            evt = sub.get(timeout=5.0)
            assert evt.kind == "data-hint"
        finally:
            srv.watcher.bus.unsubscribe(sub)

    def test_save_new_dataset(self, server, tmp_path):
        srv, ws = server
        new_path = ws / "data" / "newds.ndjson"
        d = _post(
            "/api/resource/save",
            {"resource": _patient("z1"), "dataset_path": str(new_path)},
        )
        assert d["ok"] is True
        assert new_path.exists()
        assert json.loads(new_path.read_text().splitlines()[0])["id"] == "z1"

    def test_save_escapes_workspace(self, server):
        d = _post(
            "/api/resource/save",
            {
                "resource": _patient("evil"),
                "dataset_path": "/etc/passwd",
            },
        )
        assert d["ok"] is False

    def test_save_invalid_resource_blocked(self, server):
        srv, ws = server
        target = ws / "data" / "patients.ndjson"
        before = target.read_text()
        d = _post(
            "/api/resource/save",
            {"resource": {"resourceType": "Patient", "id": ""}, "dataset_path": str(target)},
        )
        assert d["ok"] is False
        assert target.read_text() == before

    def test_save_non_object(self, server):
        d = _post(
            "/api/resource/save",
            {"resource": 42, "dataset_path": "whatever"},
        )
        assert d["ok"] is False
