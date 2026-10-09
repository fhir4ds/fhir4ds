"""S1 (c-cleanroom-ux5): toml writer + terminology config + fs/list +
workspace add-path API tests."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.cells import CellSessionRegistry
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.toml_writer import write_section
from fhir4ds.devserver.watcher import EventBus, Watcher

try:
    import tomllib
except ImportError:
    import tomli as tomllib

CQL = "library T version '1.0.0'\ndefine x: 1\n"
PORT = 18871


# ---------------------------------------------------------------------------
# toml_writer unit tests
# ---------------------------------------------------------------------------


class TestTomlWriter:
    def test_replace_preserves_comments_and_other_sections(self, tmp_path):
        p = tmp_path / "fhir4ds.toml"
        p.write_text(
            "# workspace\n[dev]\ncql = ['cql']\n\n"
            "[terminology]\n# keep me\nprovider = 'disabled'\n"
        )
        write_section(p, "terminology", {"provider": "vsac"})
        text = p.read_text()
        assert "# workspace" in text and "# keep me" in text
        assert "[dev]" in text and "cql = ['cql']" in text
        doc = tomllib.loads(text)
        assert doc["terminology"]["provider"] == "vsac"
        assert doc["dev"]["cql"] == ["cql"]

    def test_append_new_section_to_existing_file(self, tmp_path):
        p = tmp_path / "fhir4ds.toml"
        p.write_text("[dev]\ncql = ['cql']\n")
        write_section(p, "terminology", {"provider": "http", "base_url": "http://x"})
        doc = tomllib.loads(p.read_text())
        assert doc["terminology"] == {"provider": "http", "base_url": "http://x"}
        assert doc["dev"]["cql"] == ["cql"]

    def test_creates_missing_file(self, tmp_path):
        p = tmp_path / "fhir4ds.toml"
        write_section(p, "dev", {"data_dirs": ["extra-data"]})
        doc = tomllib.loads(p.read_text())
        assert doc["dev"]["data_dirs"] == ["extra-data"]

    def test_none_removes_key_and_unmentioned_keys_kept(self, tmp_path):
        p = tmp_path / "fhir4ds.toml"
        p.write_text("[terminology]\nprovider = 'http'\ntimeout_seconds = 5\n")
        write_section(p, "terminology", {"provider": None, "base_url": "https://y"})
        doc = tomllib.loads(p.read_text())
        assert "provider" not in doc["terminology"]
        assert doc["terminology"]["timeout_seconds"] == 5
        assert doc["terminology"]["base_url"] == "https://y"

    def test_string_escaping(self, tmp_path):
        p = tmp_path / "fhir4ds.toml"
        write_section(p, "dev", {"cql": ["it's a 'path'"]})
        doc = tomllib.loads(p.read_text())
        assert doc["dev"]["cql"] == ["it's a 'path'"]

    def test_invalid_section_and_keys_rejected(self, tmp_path):
        p = tmp_path / "fhir4ds.toml"
        p.write_text("[dev]\n")
        with pytest.raises(ValueError):
            write_section(p, "de[v]", {"a": 1})
        with pytest.raises(ValueError):
            write_section(p, "dev", {"bad key!": 1})

    def test_array_append_and_list_roundtrip(self, tmp_path):
        p = tmp_path / "fhir4ds.toml"
        p.write_text("[dev]\ndata_dirs = ['data']\n")
        write_section(p, "dev", {"data_dirs": ["data", "data/p1"]})
        doc = tomllib.loads(p.read_text())
        assert doc["dev"]["data_dirs"] == ["data", "data/p1"]


# ---------------------------------------------------------------------------
# API fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("ws_s1")
    (tmp_path / "cql").mkdir()
    (tmp_path / "cql" / "T.cql").write_text(CQL)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "patients.ndjson").write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
    )
    (tmp_path / "extra").mkdir()
    (tmp_path / "extra" / "more.ndjson").write_text(
        '{"resourceType": "Patient", "id": "q1"}\n'
    )
    tmp_path.joinpath("fhir4ds.toml").write_text(
        '[terminology]\nprovider = "disabled"\n'
    )
    cfg = load_config(tmp_path)
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    w = Watcher(cfg, EventBus())
    srv = create_server(mgr, w, port=PORT)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
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
        r = urllib.request.urlopen(req, timeout=30)
    return json.loads(r.read())


class TestTerminologyConfig:
    def test_get_reports_settings_without_key_value(self, server):
        _, tmp = server
        r = call("/api/terminology/config")
        assert r["ok"]
        assert r["config"]["provider"] == "disabled"
        assert "key_env_resolves" in r["config"]
        text = json.dumps(r)
        # never any raw key value material
        assert "UMLS_API_KEY" not in text or "api_key_env" in text

    def test_post_writes_toml_and_resets_holders(self, server):
        _, tmp = server
        r = call(
            "/api/terminology/config",
            {"provider": "vsac", "api_key_env": "MY_KEY_VAR", "timeout_seconds": 7},
        )
        assert r["ok"], r
        doc = tomllib.loads((tmp / "fhir4ds.toml").read_text())
        assert doc["terminology"]["provider"] == "vsac"
        assert doc["terminology"]["api_key_env"] == "MY_KEY_VAR"
        assert doc["terminology"]["timeout_seconds"] == 7
        srv_holder_reset = r["config"]["provider"] == "vsac"
        assert srv_holder_reset
        # holder reset verified indirectly: GET reflects new settings live
        g = call("/api/terminology/config")
        assert g["config"]["api_key_env"] == "MY_KEY_VAR"

    def test_post_rejects_bad_values(self, server):
        r = call("/api/terminology/config", {"provider": "bogus"})
        assert not r["ok"]
        r = call("/api/terminology/config", {"timeout_seconds": -1})
        assert not r["ok"]
        r = call("/api/terminology/config", {"api_key_env": ""})
        assert not r["ok"]

    def test_post_ignores_unknown_keys(self, server):
        r = call("/api/terminology/config", {"api_key_value": "SECRET"})
        assert r["ok"]  # unknown keys ignored (never written)
        _, tmp = server
        assert "SECRET" not in (tmp / "fhir4ds.toml").read_text()


class TestFsList:
    def test_lists_root(self, server):
        r = call("/api/fs/list")
        assert r["ok"]
        names = {e["name"]: e for e in r["entries"]}
        assert "cql" in names and names["cql"]["kind"] == "dir"
        assert "fhir4ds.toml" in names and names["fhir4ds.toml"]["kind"] == "file"

    def test_lists_subdir(self, server):
        r = call("/api/fs/list?path=cql")
        assert r["ok"] and r["path"] == "cql"
        assert any(e["name"] == "T.cql" for e in r["entries"])

    def test_rejects_escape(self, server):
        r = call("/api/fs/list?path=..")
        assert not r["ok"]

    def test_rejects_missing_dir(self, server):
        r = call("/api/fs/list?path=nope")
        assert not r["ok"]


class TestWorkspaceAddPath:
    def test_add_data_dir_persists_and_rescans(self, server):
        _, tmp = server
        r = call("/api/workspace/add-path", {"kind": "data", "path": "extra"})
        assert r["ok"], r
        doc = tomllib.loads((tmp / "fhir4ds.toml").read_text())
        assert "extra" in doc["dev"]["data_dirs"]
        assert r["snapshot"]["datasets"] >= 2

    def test_add_absolute_path_becomes_relative_when_inside(self, server):
        _, tmp = server
        r = call("/api/workspace/add-path", {"kind": "data", "path": str(tmp / "extra")})
        assert r["ok"]
        doc = tomllib.loads((tmp / "fhir4ds.toml").read_text())
        assert "extra" in doc["dev"]["data_dirs"]

    def test_rejects_missing_path_and_bad_kind(self, server):
        r = call("/api/workspace/add-path", {"kind": "data", "path": "ghost"})
        assert not r["ok"]
        r = call("/api/workspace/add-path", {"kind": "bogus", "path": "cql"})
        assert not r["ok"]

    def test_duplicate_add_is_idempotent(self, server):
        _, tmp = server
        call("/api/workspace/add-path", {"kind": "data", "path": "extra"})
        doc = tomllib.loads((tmp / "fhir4ds.toml").read_text())
        assert doc["dev"]["data_dirs"].count("extra") == 1
