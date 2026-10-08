"""API tests for the terminology cleanroom integration (VSAC/HTTP provider)."""

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
    "valueset \"BPVS\": 'http://example.com/vs1'\n"
    "valueset \"Remote\": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1061'\n\n"
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

REMOTE_CODES = [
    ("http://snomed.info/sct", "123456", "Sno 1"),
    ("http://snomed.info/sct", "789012", "Sno 2"),
    ("http://www.ama-assn.org/go/cpt", "99213", "Office visit"),
]

PORT = 19125


class FakeEndpoint:
    """Deterministic in-process endpoint (mirrors the smoke fixture)."""

    def expand(self, url):
        if "2.16.840.1.113883.3.464" not in url:
            raise LookupError(f"value set not found: {url}")
        class _C:
            def __init__(self, s, c, d):
                self.system, self.code, self.display = s, c, d
        return [_C(s, c, d) for (s, c, d) in REMOTE_CODES]

    def expand_intensional(self, value_set):
        return []

    def search_text(self, query, category=None, mode="hybrid"):
        return []

    def search_batch(self, queries, mode="hybrid"):
        return [[] for _ in queries]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("wsterm")
    (tmp_path / "cql").mkdir()
    (tmp_path / "cql" / "Demographics.cql").write_text(CQL)
    (tmp_path / "valuesets").mkdir()
    (tmp_path / "valuesets" / "vs1.json").write_text(json.dumps(VS))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "patients.ndjson").write_text(
        '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n'
    )
    (tmp_path / "fhir4ds.toml").write_text(
        "[terminology]\nprovider = \"vsac\"\napi_key_env = \"UMLS_API_KEY_TEST\"\n"
    )
    cfg = load_config(tmp_path)
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    w = Watcher(cfg, EventBus())
    srv = create_server(mgr, w, port=PORT)
    srv._terminology_endpoint_holder = FakeEndpoint()
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


class TestHealthStatus:
    def test_status_shape_no_key_material(self, server):
        h = call("/health")
        term = h["terminology"]
        assert term["provider"] == "vsac"
        assert term["configured"] is True
        assert term["api_key_set"] in (True, False)
        assert "UMLS_API_KEY" not in json.dumps(h)
        assert "apikey" not in json.dumps(h)


class TestPreview:
    def test_preview_ok_no_disk_write(self, server):
        p = call(
            "/api/terminology/preview",
            {"url": "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1061"},
        )
        assert p["ok"] is True
        assert p["count"] == 3
        assert any(c["code"] == "99213" for c in p["concepts"])

    def test_preview_unknown_typed_error(self, server):
        p = call("/api/terminology/preview", {"url": "http://example.com/nope"})
        assert p["ok"] is False
        assert "not found" in p["diagnostics"][0]["message"]

    def test_preview_missing_url(self, server):
        p = call("/api/terminology/preview", {})
        assert p["ok"] is False


class TestImport:
    def test_import_writes_file_with_provenance(self, server):
        r = call(
            "/api/terminology/import",
            {
                "url": "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1061",
                "name": "OfficeVisitLocal",
            },
        )
        assert r["ok"] is True
        assert r["stale"] is True
        srv, tmp = server
        path = tmp / "valuesets" / "OfficeVisitLocal.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["_origin"]["imported_from"].startswith("http://cts.nlm")
        assert data["_origin"]["code_count"] == 3
        systems = {i["system"] for i in data["compose"]["include"]}
        assert len(systems) == 2

    def test_import_rejects_bad_name(self, server):
        r = call(
            "/api/terminology/import",
            {"url": "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1061",
             "name": "../escape"},
        )
        assert r["ok"] is False
        assert "identifier" in r["diagnostics"][0]["message"]


class TestResolution:
    def test_local_vsac_unresolved(self, server):
        rows = call("/api/terminology/resolution")["resolutions"]
        by_id = {row["id"]: row for row in rows}
        assert by_id["BPVS"]["resolved"] == "local"
        assert by_id["Remote"]["resolved"] == "VSAC"


class TestDisabled:
    def test_disabled_provider_preview(self, tmp_path):
        (tmp_path / "cql").mkdir()
        (tmp_path / "cql" / "L.cql").write_text(
            "library L version '1.0.0'\nusing FHIR version '4.0.1'\n\ndefine X: true\n"
        )
        (tmp_path / "data").mkdir()
        cfg = load_config(tmp_path)
        snap = scan_workspace(cfg)
        mgr = KernelManager(snap)
        w = Watcher(cfg, EventBus())
        srv = create_server(mgr, w, port=PORT + 1)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.2)
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{PORT + 1}/api/terminology/preview",
                data=json.dumps({"url": "http://x/y"}).encode(),
                headers={"Content-Type": "application/json"},
            )
            body = json.loads(urllib.request.urlopen(req, timeout=30).read())
            assert body["ok"] is False
            assert "disabled" in body["diagnostics"][0]["message"]
        finally:
            srv.shutdown()
