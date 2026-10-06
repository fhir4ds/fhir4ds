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


class TestCompare:
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
                "scoring": "proportion",
                "measure_name": "MyMeasure",
            },
        )["measure"]

    def _expected(self, measure_url, num_counts):
        def mr(pid, ip, num):
            return {
                "resourceType": "MeasureReport",
                "status": "complete",
                "type": "individual",
                "measure": measure_url,
                "subject": {"reference": f"Patient/{pid}"},
                "group": [
                    {
                        "id": "group-1",
                        "population": [
                            {
                                "code": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/measure-population", "code": "initial-population"}]},
                                "count": ip,
                            },
                            {
                                "code": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/measure-population", "code": "numerator"}]},
                                "count": num,
                            },
                        ],
                    }
                ],
            }

        return [mr(f"p{i}", 1, 1 if (i % 2 and num_counts == "odd") else (1 if num_counts == "all" else 0)) for i in range(1, 7)]

    def test_compare_pass(self, server):
        srv, _ = server
        m = self._scaffold(srv)
        liburl = m["library"][0]
        exp = self._expected(liburl, "odd")
        d = call(srv, "/api/measure/compare", {"library": "Demo", "measure": m, "expected": exp})
        assert d["ok"] is True
        assert d["passed"] is True
        assert d["strict"] is False
        rows = {r["code"]: r for r in d["rows"]}
        assert rows["initial-population"] == {"code": "initial-population", "expected": 6, "actual": 6, "delta": 0}
        assert rows["numerator"]["delta"] == 0
        assert d["expected_measure"]["matches"] is True

    def test_compare_fail_delta(self, server):
        srv, _ = server
        m = self._scaffold(srv)
        liburl = m["library"][0]
        exp = self._expected(liburl, "all")
        d = call(srv, "/api/measure/compare", {"library": "Demo", "measure": m, "expected": exp})
        assert d["ok"] is True
        assert d["passed"] is False
        rows = {r["code"]: r for r in d["rows"]}
        assert rows["numerator"]["expected"] == 6
        assert rows["numerator"]["actual"] == 3
        assert rows["numerator"]["delta"] == -3

    def test_compare_canonical_mismatch(self, server):
        srv, _ = server
        m = self._scaffold(srv)
        exp = self._expected("http://example.com/other-measure", "odd")
        d = call(srv, "/api/measure/compare", {"library": "Demo", "measure": m, "expected": exp})
        assert d["ok"] is True
        assert d["expected_measure"]["matches"] is False
        assert d["expected_measure"]["canonical"] == "http://example.com/other-measure"

    def test_compare_strict_vs_loose(self, server):
        srv, _ = server
        m = self._scaffold(srv)
        liburl = m["library"][0]
        # one merged report w/ aggregate counts: loose passes, strict fails
        merged = self._expected(liburl, "odd")[:1]
        merged[0]["group"][0]["population"][0]["count"] = 6
        merged[0]["group"][0]["population"][1]["count"] = 3
        loose = call(srv, "/api/measure/compare", {"library": "Demo", "measure": m, "expected": merged, "strict": False})
        strict = call(srv, "/api/measure/compare", {"library": "Demo", "measure": m, "expected": merged, "strict": True})
        assert loose["ok"] is True and loose["passed"] is True
        assert strict["ok"] is True and strict["passed"] is False

    def test_compare_invalid_shapes(self, server):
        srv, _ = server
        m = self._scaffold(srv)
        d1 = call(srv, "/api/measure/compare", {"library": "Demo", "measure": m, "expected": "not-a-list"})
        assert d1["ok"] is False
        d2 = call(srv, "/api/measure/compare", {"library": "Demo", "measure": {"resourceType": "Patient"}, "expected": []})
        assert d2["ok"] is False
        assert "Measure" in d2["diagnostics"][0]["message"]

    def test_compare_with_text(self, server):
        srv, _ = server
        m = self._scaffold(srv)
        liburl = m["library"][0]
        exp = self._expected(liburl, "odd")
        d = call(srv, "/api/measure/compare", {"library": "Demo", "text": CQL, "measure": m, "expected": exp})
        assert d["ok"] is True and d["passed"] is True
