"""Static UI serving tests."""

from __future__ import annotations

import threading
import time
import urllib.request

import pytest

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import EventBus, Watcher

PORT = 18802

STATIC_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent / "static"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("ws-empty")
    cfg = load_config(tmp_path)
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    w = Watcher(cfg, EventBus())
    srv = create_server(mgr, w, port=PORT)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    yield srv
    srv.shutdown()


def fetch(path):
    return urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=10)


@pytest.mark.skipif(
    not (STATIC_ROOT / "index.html").exists(), reason="built UI not committed yet"
)
class TestStaticUI:
    def test_index_served(self, server):
        body = fetch("/").read()
        assert b'<div id="root">' in body

    def test_asset_served(self, server):
        import re

        idx = fetch("/").read()
        m = re.search(rb"assets/index-[^\"]+\.js", idx)
        assert m, "index references the hashed bundle"
        js = fetch("/" + m.group().decode()).read()
        assert len(js) > 100_000  # the React bundle

    def test_traversal_blocked(self, server):
        with pytest.raises(urllib.error.HTTPError) as exc:
            fetch("/assets/..%2f..%2fetc%2fpasswd")
        assert exc.value.code == 404

    def test_api_still_routes(self, server):
        body = fetch("/health").read()
        assert b'"ok"' in body
