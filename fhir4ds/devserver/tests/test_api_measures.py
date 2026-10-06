"""API tests for the measure scaffold/run routes (v3 slice 2)."""
import json
import threading
import time
from pathlib import Path

import pytest

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import EventBus, Watcher

PORT = 18891

CQL = """library Demo version '1.0.0'
using FHIR version '4.0.1'

valueset "BPVS": 'http://example.com/bp'

context Patient

// # %% [name: InIp]
define InIp: true

// # %% [name: HasBp]
define HasBp: exists([Observation] O where O.code in "BPVS")
"""

VS = {
    "resourceType": "ValueSet",
    "id": "bp",
    "url": "http://example.com/bp",
    "compose": {"include": [{"system": "http://loinc.org", "concept": [{"code": "8480-6"}]}]},
}

PATIENTS = []
for i in range(1, 7):
    pid = f"p{i}"
    pat = {"resourceType": "Patient", "id": pid, "gender": "male" if i % 2 else "female"}
    obs = None
    if i % 2:
        obs = {
            "resourceType": "Observation",
            "id": f"o{i}",
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6"}]},
            "subject": {"reference": f"Patient/{pid}"},
        }
    PATIENTS.append(pat)
    if obs:
        PATIENTS.append(obs)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    ws = tmp_path_factory.mktemp("ms_ws")
    (ws / "cql").mkdir()
    (ws / "valuesets").mkdir()
    (ws / "data").mkdir()
    (ws / "cql" / "Demo.cql").write_text(CQL)
    (ws / "valuesets" / "bp.json").write_text(json.dumps(VS))
    with open(ws / "data" / "patients.ndjson", "w") as fh:
        for r in PATIENTS:
            fh.write(json.dumps(r) + "\n")
    cfg = load_config(str(ws))
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    watcher = Watcher(cfg, EventBus())
    srv = create_server(mgr, watcher, port=PORT)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.2)
    yield srv, ws
    srv.shutdown()


def call(srv, path, body=None):
    import urllib.request, urllib.error

    url = f"http://127.0.0.1:{PORT}{path}"
    if body is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
        )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:  # pragma: no cover
        return json.loads(e.read())


class TestScaffold:
    def test_bootstrap(self, server):
        srv, _ = server
        d = call(srv, "/api/measure/scaffold", {"library": "Demo"})
        assert d["ok"] is True
        assert d["mapping"] == []
        m = d["measure"]
        assert m["resourceType"] == "Measure"
        assert m["group"][0]["population"] == []
        assert m["scoring"]["coding"][0]["code"] == "proportion"

    def test_with_mapping_and_scoring(self, server):
        srv, _ = server
        d = call(
            srv,
            "/api/measure/scaffold",
            {
                "library": "Demo",
                "mapping": [
                    {"define": "InIp", "code": "initial-population"},
                    {"define": "HasBp", "code": "numerator"},
                ],
                "scoring": "ratio",
                "measure_name": "MyMeasure",
            },
        )
        assert d["ok"] is True
        m = d["measure"]
        assert m["name"] == "MyMeasure"
        assert m["scoring"]["coding"][0]["code"] == "ratio"
        codes = [p["code"]["coding"][0]["code"] for p in m["group"][0]["population"]]
        assert codes == ["initial-population", "numerator"]

    def test_bad_mapping_shape(self, server):
        srv, _ = server
        d = call(srv, "/api/measure/scaffold", {"library": "Demo", "mapping": "nope"})
        assert d["ok"] is False
        assert "mapping must be a list" in d["diagnostics"][0]["message"]

    def test_bad_scoring(self, server):
        srv, _ = server
        d = call(srv, "/api/measure/scaffold", {"library": "Demo", "scoring": "bogus"})
        assert d["ok"] is False
        assert "unknown scoring code" in d["diagnostics"][0]["message"]

    def test_unknown_define(self, server):
        srv, _ = server
        d = call(
            srv,
            "/api/measure/scaffold",
            {"library": "Demo", "mapping": [{"define": "Nope", "code": "numerator"}]},
        )
        assert d["ok"] is False


class TestRun:
    def _scaffold(self, srv):
        return call(
            srv,
            "/api/measure/scaffold",
            {
                "library": "Demo",
                "mapping": [
                    {"define": "InIp", "code": "initial-population"},
                    {"define": "HasBp", "code": "numerator"},
                ],
            },
        )["measure"]

    def test_happy_path_counts_and_reports(self, server):
        srv, _ = server
        m = self._scaffold(srv)
        d = call(srv, "/api/measure/run", {"library": "Demo", "measure": m})
        assert d["ok"] is True
        assert d["counts"] == {"initial_population": 6, "numerator": 3}
        assert len(d["reports"]) == 6
        r0 = d["reports"][0]
        pops = r0["group"][0]["population"]
        got = {p["code"]["coding"][0]["code"]: p["count"] for p in pops}
        if r0["subject"]["reference"] == "Patient/p1":
            assert got == {"initial-population": 1, "numerator": 1}
        else:
            assert got == {"initial-population": 1, "numerator": 0}

    def test_non_measure_rejected(self, server):
        srv, _ = server
        d = call(srv, "/api/measure/run", {"library": "Demo", "measure": {"resourceType": "Patient", "id": "x"}})
        assert d["ok"] is False
        assert "Measure" in d["diagnostics"][0]["message"]

    def test_measure_without_populations(self, server):
        srv, _ = server
        m = call(srv, "/api/measure/scaffold", {"library": "Demo"})["measure"]
        d = call(srv, "/api/measure/run", {"library": "Demo", "measure": m})
        assert d["ok"] is False

    def test_run_with_text(self, server):
        srv, _ = server
        m = self._scaffold(srv)
        d = call(srv, "/api/measure/run", {"library": "Demo", "text": CQL, "measure": m})
        assert d["ok"] is True
        assert d["counts"]["initial_population"] == 6
