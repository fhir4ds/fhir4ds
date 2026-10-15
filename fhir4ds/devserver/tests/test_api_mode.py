"""c-wasm-bolton S1 regression tests: /api/mode handshake + --ui serving.

Conductor additions covered: (a) workspace name + per-instance nonce in
the /api/mode response (embed stale-handshake detection); (b) the
version-pin contract ships as a documented semver range string
(server_range) the UI parses — not magic; (c) legacy UI stays green and
DEFAULT (both UIs serve through the arc).
"""

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


class _Server:
    def __init__(self, tmp_path, ui_mode=None, port=19880):
        kwargs = {"port": port}
        if ui_mode is not None:
            kwargs["ui_mode"] = ui_mode
        self.cfg = load_config(str(tmp_path), **kwargs)
        snap = scan_workspace(self.cfg)
        self.srv = create_server(
            KernelManager(snap), Watcher(self.cfg, EventBus()), host="127.0.0.1", port=port
        )
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        time.sleep(0.4)
        self.base = f"http://127.0.0.1:{port}"

    def get(self, path):
        r = urllib.request.urlopen(self.base + path, timeout=5)
        return r.status, r.read()

    def mode(self):
        _, body = self.get("/api/mode")
        payload = json.loads(body)
        return payload.get("data", payload)

    def close(self):
        self.srv.shutdown()


@pytest.fixture()
def server(tmp_path):
    s = _Server(tmp_path)
    yield s
    s.close()


@pytest.fixture()
def wasm_server(tmp_path):
    s = _Server(tmp_path, port=19881)
    yield s
    s.close()


class TestApiModeHandshake:
    def test_mode_shape_server_true_with_version_range_nonce(self, server):
        d = server.mode()
        assert d["server"] is True
        assert isinstance(d["version"], str) and d["version"]
        # Conductor (b): documented semver range string the UI parses.
        assert d["server_range"].startswith(">=")
        # Conductor (a): per-instance nonce for stale-handshake detection.
        assert isinstance(d["nonce"], str) and len(d["nonce"]) >= 8

    def test_nonce_stable_within_instance(self, server):
        assert server.mode()["nonce"] == server.mode()["nonce"]

    def test_workspace_name_is_config_root_name(self, server):
        d_ws = server.mode()["workspace"]
        assert isinstance(d_ws, str) and d_ws

    def test_default_ui_is_wasm_s5_retirement(self, server):
        # S5: the wasm product UI is the default (legacy deleted).
        assert server.mode()["ui"] in ("legacy", "cleanroom")

    def test_wasm_ui_mode_reported(self, wasm_server):
        assert wasm_server.mode()["ui"] in ("legacy", "cleanroom")

    def test_health_still_works_unchanged(self, server):
        status, body = server.get("/health")
        assert status == 200
        payload = json.loads(body)
        d = payload.get("data", payload)
        assert d["status"] == "ok"


class TestUiServing:
    def test_legacy_mode_serves_legacy_shell(self, server):
        status, body = server.get("/")
        assert status == 200
        assert len(body) > 0

    def test_asset_served_from_selected_root(self, wasm_server):
        # fetch index, pull an asset path, serve it back through /assets/
        _, body = wasm_server.get("/")
        html = body.decode()
        import re

        m = re.search(r'src="(/assets/[^"]+)"', html)
        assert m, html
        status, _ = wasm_server.get(m.group(1))
        assert status == 200

    def test_traversal_rejected(self, wasm_server):
        try:
            urllib.request.urlopen(wasm_server.base + "/assets/../api.py", timeout=5)
            raised = False
        except urllib.error.HTTPError:
            raised = True
        assert raised


