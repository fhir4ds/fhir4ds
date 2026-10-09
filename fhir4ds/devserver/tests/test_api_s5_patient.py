"""S5 (c-cleanroom-ux5 item 7): /api/patient/resources route."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from fhir4ds.cql.loader import FHIRDataLoader
from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import EventBus, Watcher

PORT = 18886

CQL = "library S5Host\ndefine A: 1\n"

RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "gender": "male", "birthDate": "1980-01-01"},
    {
        "resourceType": "Observation",
        "id": "o1",
        "status": "final",
        "code": {"text": "BP"},
        "subject": {"reference": "Patient/p1"},
        "effectiveDateTime": "2026-01-15T10:00:00Z",
        "valueQuantity": {"value": 120, "unit": "mmHg"},
    },
    {
        "resourceType": "Condition",
        "id": "c1",
        "clinicalStatus": {"coding": [{"code": "active"}]},
        "code": {"text": "HTN"},
        "subject": {"reference": "Patient/p1"},
    },
    {"resourceType": "Patient", "id": "p2", "gender": "female"},
]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("ws_s5")
    (tmp_path / "cql").mkdir()
    (tmp_path / "cql" / "S5Host.cql").write_text(CQL)
    cfg = load_config(tmp_path)
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    kernel = mgr.current()
    loader = FHIRDataLoader(kernel.conn)
    loader.load_resources(RESOURCES)
    w = Watcher(cfg, EventBus())
    srv = create_server(mgr, w, port=PORT)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    yield srv
    srv.shutdown()


def get(path):
    r = urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=60)
    return json.loads(r.read())


class TestPatientResources:
    def test_grouped_by_type(self, server):
        r = get("/api/patient/resources?id=p1")
        assert r["ok"]
        assert r["total"] == 3
        assert set(r["by_type"]) == {"Patient", "Observation", "Condition"}
        obs = r["by_type"]["Observation"][0]
        assert obs["id"] == "o1"
        assert obs["status"] == "final"
        assert obs["date"] == "2026-01-15T10:00:00Z"
        assert len(obs["preview"]) <= 200

    def test_other_patient_isolated(self, server):
        r = get("/api/patient/resources?id=p2")
        assert r["ok"]
        assert r["total"] == 1
        assert list(r["by_type"]) == ["Patient"]

    def test_missing_id_rejected(self, server):
        r = get("/api/patient/resources?id=")
        assert not r["ok"]

    def test_unknown_patient_empty(self, server):
        r = get("/api/patient/resources?id=nobody")
        assert r["ok"]
        assert r["total"] == 0
        assert r["by_type"] == {}
