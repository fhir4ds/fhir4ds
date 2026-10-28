"""v4.3 api tests: view/run explicit resources + constants end-to-end."""
import json
import threading
import time

import pytest
import urllib.request

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import EventBus, Watcher

CQL = """library Demographics version '1.0.0'
using FHIR version '4.0.1'

valueset "BPVS": 'http://example.com/bp'

context Patient

// # %% [name: InIp]
define InIp: true

// # %% [name: HasBp]
define HasBp: exists([Observation] O where O.code in "BPVS")
"""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    ws = tmp_path_factory.mktemp("ws")
    (ws / "cql").mkdir()
    (ws / "valuesets").mkdir()
    (ws / "data").mkdir()
    (ws / "cql" / "Demographics.cql").write_text(CQL)
    (ws / "valuesets" / "vs1.json").write_text(
        json.dumps(
            {
                "resourceType": "ValueSet",
                "id": "vs1",
                "url": "http://example.com/bp",
                "compose": {"include": [{"system": "http://loinc.org", "concept": [{"code": "8480-6"}]}]},
            }
        )
    )
    lines = []
    for i in range(1, 7):
        lines.append(
            json.dumps(
                {
                    "resourceType": "Patient",
                    "id": f"p{i}",
                    "gender": "male" if i % 2 else "female",
                }
            )
        )
        if i % 2:
            lines.append(
                json.dumps(
                    {
                        "resourceType": "Observation",
                        "id": f"o{i}",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6"}]},
                        "subject": {"reference": f"Patient/p{i}"},
                    }
                )
            )
    (ws / "data" / "patients.ndjson").write_text("\n".join(lines) + "\n")

    cfg = load_config(str(ws))
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    watcher = Watcher(cfg, EventBus())
    srv = create_server(mgr, watcher, port=19035)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)
    yield srv, str(ws)
    srv.shutdown()


def post(srv, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.server_address[1]}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req).read())


MR_VD = {
    "resource": "MeasureReport",
    "name": "MrFlat",
    "select": [{"column": [{"name": "subject", "path": "subject.reference"}]}],
}


def _measure_reports(srv):
    sc = post(
        srv,
        "/api/measure/scaffold",
        {
            "library": "Demographics",
            "mapping": [
                {"define": "InIp", "code": "initial-population"},
                {"define": "HasBp", "code": "numerator"},
            ],
            "scoring": "proportion",
            "measure_name": "MyMeasure",
        },
    )
    assert sc["ok"], sc
    r = post(srv, "/api/measure/run", {"library": "Demographics", "measure": sc["measure"]})
    assert r["ok"], r
    return r["reports"]


def test_view_run_over_explicit_measure_reports(server):
    srv, _ = server
    reports = _measure_reports(srv)
    r = post(srv, "/api/view/run", {"text": json.dumps(MR_VD), "resources": reports})
    assert r["ok"], r.get("diagnostics")
    assert len(r["rows"]) == 6
    assert r["rows"][0]["subject"] == "Patient/p1"
    assert r["resource_count"] == 6


def test_view_run_explicit_resources_shape_errors(server):
    srv, _ = server
    for bad in ("nope", [42], [{"a": 1}, "x"]):
        r = post(srv, "/api/view/run", {"text": json.dumps(MR_VD), "resources": bad})
        assert not r["ok"], bad
        assert "list of JSON objects" in r["diagnostics"][0]["message"]


def test_view_run_dataset_mode_regression(server):
    srv, _ = server
    vd = {"resource": "Patient", "name": "PxDemo", "select": [{"column": [{"name": "id", "path": "id"}]}]}
    r = post(srv, "/api/view/run", {"text": json.dumps(vd)})
    assert r["ok"] and len(r["rows"]) == 6, r


def test_view_run_constants_end_to_end(server):
    srv, _ = server
    vd = {
        "resource": "Patient",
        "name": "PxC",
        "constant": [{"name": "tag", "valueString": "demo"}],
        "select": [{"column": [{"name": "id", "path": "id"}, {"name": "tag", "path": "%tag"}]}],
    }
    r = post(srv, "/api/view/run", {"text": json.dumps(vd)})
    assert r["ok"], r.get("diagnostics")
    assert r["rows"][0]["tag"] == "demo"
