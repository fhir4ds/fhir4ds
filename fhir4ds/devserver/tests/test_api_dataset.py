"""API tests for the v4.4 dataset pane routes (GET /api/dataset)."""

import json
import os
import threading
import time
import urllib.request
from urllib.parse import quote

import pytest

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import EventBus, Watcher

PORT = 19061
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    ws = tmp_path_factory.mktemp("ws")
    (ws / "cql").mkdir()
    (ws / "valuesets").mkdir()
    (ws / "data").mkdir()
    (ws / "cql" / "Demographics.cql").write_text(
        "library Demographics version '1.0.0'\n"
        "using FHIR version '4.0.1'\n\n"
        "valueset \"BPVS\": 'http://example.com/bp'\n\n"
        "// # %% [name: IsMale]\n"
        "define IsMale: Patient.gender = 'male'\n"
    )
    (ws / "valuesets" / "vs1.json").write_text(
        json.dumps(
            {
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
            },
            indent=2,
        )
    )
    with open(ws / "data" / "patients.ndjson", "w") as f:
        for i in range(1, 7):
            f.write(
                json.dumps(
                    {
                        "resourceType": "Patient",
                        "id": f"p{i}",
                        "gender": "male" if i % 2 == 1 else "female",
                    }
                )
                + "\n"
            )
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


def _get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read().decode())


class TestDatasetRoute:
    def test_read_happy(self, server):
        srv, ws = server
        dpath = str(ws / "data" / "patients.ndjson")
        d = _get("/api/dataset?path=" + quote(dpath))
        assert d["ok"] is True
        assert d["path"] == dpath
        assert len(d["resources"]) == 6
        assert d["resources"][0]["resourceType"] == "Patient"
        assert d["resources"][0]["id"] == "p1"
        assert d["parse_errors"] == []

    def test_unknown_path_rejected(self, server):
        d = _get("/api/dataset?path=" + quote("/etc/passwd"))
        assert d["ok"] is False
        assert "unknown dataset path" in d["diagnostics"][0]["message"]

    def test_missing_param(self, server):
        d = _get("/api/dataset")
        assert d["ok"] is False

    def test_parse_errors_attributed(self, server):
        srv, ws = server
        bad = ws / "data" / "bad.ndjson"
        # Snapshot only knows patients.ndjson; the guard rejects unknown
        # paths, so parse errors must be probed by REPLACING the known file
        # content, reading, then restoring.
        good = ws / "data" / "patients.ndjson"
        original = good.read_text()
        try:
            good.write_text('{"resourceType": "Patient", "id": "p1"}\n{oops\n')
            d = _get("/api/dataset?path=" + quote(str(good)))
            assert d["ok"] is True
            assert len(d["resources"]) == 1
            assert len(d["parse_errors"]) == 1
            assert d["parse_errors"][0]["line"] == 2
            assert "oosp" not in d["parse_errors"][0]["error"]  # msg content free
        finally:
            good.write_text(original)
