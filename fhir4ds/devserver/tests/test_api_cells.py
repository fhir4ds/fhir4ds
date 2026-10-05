"""WS cells-protocol integration tests (handshake, sync, run, errors)."""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import threading
import time
import urllib.request

import pytest

from fhir4ds.devserver.api import create_server
from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.kernel import KernelManager
from fhir4ds.devserver.watcher import EventBus, Watcher

PORT = 18861

CQL = """library Demo version '1.0.0'
using FHIR version '4.0.1'

context Patient

// # %% [name: Male]
define Male: Patient.gender = 'male'

// # %% [name: Females]
define Females: Patient.gender = 'female'
"""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("cells-ws")
    (tmp_path / "cql").mkdir()
    (tmp_path / "cql" / "Demo.cql").write_text(CQL)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "p.ndjson").write_text(
        '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n'
        '{"resourceType": "Patient", "id": "p2", "gender": "female"}\n'
    )
    cfg = load_config(tmp_path)
    snap = scan_workspace(cfg)
    mgr = KernelManager(snap)
    w = Watcher(cfg, EventBus())
    srv = create_server(mgr, w, port=PORT)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield srv
    srv.shutdown()


class WsClient:
    def __init__(self):
        self.sock = socket.create_connection(("127.0.0.1", PORT), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET /api/events HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        assert b"101" in resp.split(b"\r\n")[0]
        self.buffer = bytearray()

    def send(self, obj):
        data = json.dumps(obj).encode()
        mask = b"\x01\x02\x03\x04"
        n = len(data)
        if n < 126:
            header = struct.pack("!BB", 0x81, 0x80 | n)
        elif n < 65536:
            header = struct.pack("!BBH", 0x81, 0x80 | 126, n)
        else:
            header = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
        self.sock.sendall(
            header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        )

    def read_frame(self, timeout=30):
        self.sock.settimeout(timeout)
        try:
            while True:
                # parse one frame from buffer
                if len(self.buffer) >= 2:
                    op = self.buffer[0] & 0x0F
                    ln = self.buffer[1] & 0x7F
                    off = 2
                    if ln == 126 and len(self.buffer) >= 4:
                        ln = struct.unpack("!H", bytes(self.buffer[2:4]))[0]
                        off = 4
                    elif ln == 127 and len(self.buffer) >= 10:
                        ln = struct.unpack("!Q", bytes(self.buffer[2:10]))[0]
                        off = 10
                    if len(self.buffer) >= off + ln:
                        payload = bytes(self.buffer[off : off + ln])
                        del self.buffer[: off + ln]
                        return op, payload.decode(errors="replace")
                chunk = self.sock.recv(4096)
                if not chunk:
                    return None
                self.buffer.extend(chunk)
        except socket.timeout:
            return None

    def until(self, kinds, deadline=45):
        """Skip frames until one of `kinds` arrives; return it."""
        end = time.time() + deadline
        while time.time() < end:
            f = self.read_frame(timeout=max(1, end - time.time()))
            if f is None:
                return None
            try:
                msg = json.loads(f[1])
            except ValueError:
                continue
            if msg.get("kind") in kinds:
                return msg
        return None

    def close(self):
        self.sock.close()


@pytest.fixture()
def ws(server):
    client = WsClient()
    connected = client.until({"connected"})
    assert connected is not None
    yield client
    client.close()


def test_run_cell_auto_closure_and_result(ws):
    """Bare Run ('cell' mode) auto-includes the dependency closure in ONE
    evaluation (hotfix: previously strict single-define, so deps dangled
    with raw Binder errors)."""
    ws.send({"kind": "sync", "library": "Demo", "text": CQL})
    time.sleep(0.2)
    ws.send({"kind": "run", "library": "Demo", "cell": "Male", "mode": "cell"})
    msg = ws.until({"result", "cellerror", "runerror"})
    assert msg is not None and msg["kind"] == "result"
    # Male has no cell deps (Patient is context-filtered) -> closure is itself.
    assert msg["cells"] == ["Male"]
    rows = msg["per_cell"]["Male"]["rows"]
    assert {"Male": True} in rows and {"Male": False} in rows


def test_run_bare_cell_includes_prior_dep_results(ws):
    """The user repro: run IsMale (ok), then bare-Run MaleCount -> the
    closure composes and BOTH cells report results (deps refresh too)."""
    text = (
        "library Demo version '1.0.0'\nusing FHIR version '4.0.1'\n\ncontext Patient\n\n"
        "// # %%\ndefine IsMale: Patient.gender = 'male'\n\n"
        "// # %%\ndefine MaleCount: IsMale\n"
    )
    ws.send({"kind": "sync", "library": "Demo", "text": text})
    time.sleep(0.2)
    ws.send({"kind": "run", "library": "Demo", "cell": "IsMale", "mode": "cell"})
    first = ws.until({"result"})
    assert first is not None and first["kind"] == "result"
    ws.send({"kind": "run", "library": "Demo", "cell": "MaleCount", "mode": "cell"})
    msg = ws.until({"result", "cellerror", "runerror"})
    assert msg is not None and msg["kind"] == "result"
    assert set(msg["cells"]) == {"IsMale", "MaleCount"}
    # The target AND the refreshed dep both carry per-cell slices.
    assert "MaleCount" in msg["per_cell"] and "IsMale" in msg["per_cell"]


def test_run_cell_only_strict_mode(ws):
    """'cell_only' preserves the legacy strict single-define mode."""
    text = (
        "library Demo version '1.0.0'\nusing FHIR version '4.0.1'\n\ncontext Patient\n\n"
        "// # %%\ndefine IsMale: Patient.gender = 'male'\n\n"
        "// # %%\ndefine MaleCount: IsMale\n"
    )
    ws.send({"kind": "sync", "library": "Demo", "text": text})
    time.sleep(0.2)
    ws.send({"kind": "run", "library": "Demo", "cell": "MaleCount", "mode": "cell_only"})
    msg = ws.until({"result", "cellerror", "runerror"})
    # Strict compose of MaleCount alone dangles IsMale -> engine failure,
    # cleanly attributed (cellerror naming the requesting cell).
    assert msg is not None and msg["kind"] == "cellerror"
    assert msg["cell"] == "MaleCount"
    assert msg["cells"] == ["MaleCount"]


def test_run_bare_cell_missing_dep_clean_runerror(ws):
    """Missing dep on a bare Run surfaces a CLEAN runerror naming the
    missing cell — never a raw Binder error."""
    text = (
        "library Demo version '1.0.0'\nusing FHIR version '4.0.1'\n\ncontext Patient\n\n"
        "// # %%\ndefine IsMale: Patient.gender = 'male'\n\n"
        "// # %%\ndefine Boom: Missing\n"
    )
    ws.send({"kind": "sync", "library": "Demo", "text": text})
    time.sleep(0.2)
    ws.send({"kind": "run", "library": "Demo", "cell": "Boom", "mode": "cell"})
    msg = ws.until({"result", "cellerror", "runerror"})
    assert msg is not None and msg["kind"] == "runerror"
    assert "references Missing" in msg["message"]
    assert "run or define" in msg["message"]


def test_run_cell_deps_composes_closure(ws):
    text = (
        "library Demo version '1.0.0'\nusing FHIR version '4.0.1'\n\ncontext Patient\n\n"
        "// # %%\ndefine IsMale: Patient.gender = 'male'\n\n"
        "// # %%\ndefine MaleCount: IsMale\n"
    )
    ws.send({"kind": "sync", "library": "Demo", "text": text})
    time.sleep(0.2)
    ws.send({"kind": "run", "library": "Demo", "cell": "MaleCount", "mode": "cell_deps"})
    msg = ws.until({"result", "cellerror", "runerror"})
    assert msg is not None and msg["kind"] == "result"
    assert set(msg["cells"]) == {"IsMale", "MaleCount"}


def test_run_unknown_cell_runerror(ws):
    ws.send({"kind": "sync", "library": "Demo", "text": CQL})
    time.sleep(0.2)
    ws.send({"kind": "run", "library": "Demo", "cell": "Nope", "mode": "cell"})
    msg = ws.until({"runerror"})
    assert msg is not None and "Nope" in msg["message"]


def test_closure_error_attributes_to_requesting_cell(ws):
    """Review-note pin: a closure cell FAILING at evaluation attributes to
    the REQUESTING cell (and the split set), never silently to the wrong
    cell. Uses a runtime failure (invalid date comparison), NOT a dangling
    identifier — dangling refs now short-circuit to a clean runerror."""
    text = (
        "library Demo version '1.0.0'\nusing FHIR version '4.0.1'\n\ncontext Patient\n\n"
        "// # %%\ndefine Good: Patient.gender = 'male'\n\n"
        "// # %%\ndefine Boom: 1\n\n"
        "// # %%\ndefine Top: Good and Boom\n"
    )
    ws.send({"kind": "sync", "library": "Demo", "text": text})
    time.sleep(0.2)
    ws.send({"kind": "run", "library": "Demo", "cell": "Top", "mode": "cell_deps"})
    msg = ws.until({"result", "cellerror", "runerror"})
    assert msg is not None and msg["kind"] == "cellerror"
    # The error names the REQUESTING cell; the whole split set is listed.
    assert msg["cell"] == "Top"
    assert set(msg["cells"]) == {"Good", "Boom", "Top"}


def test_closure_dangling_ref_is_clean_runerror(ws):
    """Dangling refs in the closure short-circuit to a CLEAN runerror
    naming the missing cell (previously raw Binder via cellerror)."""
    text = (
        "library Demo version '1.0.0'\nusing FHIR version '4.0.1'\n\ncontext Patient\n\n"
        "// # %%\ndefine Good: Patient.gender = 'male'\n\n"
        "// # %%\ndefine Boom: Missing\n\n"
        "// # %%\ndefine Top: Good and Boom\n"
    )
    ws.send({"kind": "sync", "library": "Demo", "text": text})
    time.sleep(0.2)
    ws.send({"kind": "run", "library": "Demo", "cell": "Top", "mode": "cell_deps"})
    msg = ws.until({"result", "cellerror", "runerror"})
    assert msg is not None and msg["kind"] == "runerror"
    assert "references Missing" in msg["message"]


def test_deleted_cell_drop_condition(ws):
    """Review-note pin: the exact drop condition for deleted cells — the
    failing rerun of a dependent drops the deleted cell's record."""
    text = (
        "library Demo version '1.0.0'\nusing FHIR version '4.0.1'\n\ncontext Patient\n\n"
        "// # %%\ndefine Base: Patient.gender = 'male'\n\n"
        "// # %%\ndefine UsesBase: Base\n"
    )
    ws.send({"kind": "sync", "library": "Demo", "text": text})
    time.sleep(0.2)
    ws.send({"kind": "run", "library": "Demo", "cell": "UsesBase", "mode": "cell_deps"})
    ok = ws.until({"result"})
    assert ok is not None and ok["kind"] == "result"
    # Delete Base; UsesBase now dangles.
    text2 = text.replace(
        "// # %%\ndefine Base: Patient.gender = 'male'\n\n", ""
    )
    ws.send({"kind": "sync", "library": "Demo", "text": text2})
    time.sleep(0.2)
    # Hotfix: bare Run auto-includes closure; with Base deleted the dep is
    # missing everywhere -> CLEAN runerror naming Base (not raw Binder).
    ws.send({"kind": "run", "library": "Demo", "cell": "UsesBase", "mode": "cell"})
    err = ws.until({"result", "cellerror", "runerror"})
    assert err is not None and err["kind"] == "runerror"
    assert "references Base" in err["message"]


def test_run_with_inline_text_overrides(ws):
    """run-with-text: the buffer text is authoritative (Apply doctrine)."""
    edited = CQL.replace("'male'", "'MALE'")
    ws.send({"kind": "run", "library": "Demo", "cell": "Male", "mode": "cell", "text": edited})
    msg = ws.until({"result", "cellerror", "runerror"})
    assert msg is not None and msg["kind"] == "result"
    rows = msg["per_cell"]["Male"]["rows"]
    # 'MALE' never matches -> all False (engine lowercases nothing).
    assert all(r["Male"] is False for r in rows)


class TestCollectionLiteralClosureApi:
    """v2 verification blocker: run cell_deps over WS on a cell whose dep is
    referenced inside a collection-literal function argument (Count({IsMale}))
    — the closure must compose IsMale and evaluate, not Binder-error."""

    _LIB = (
        "library Demo version '1.0.0'\n"
        "using FHIR version '4.0.1'\n"
        "context Patient\n"
        "\n"
        "// # %% [name: IsMale]\n"
        "define IsMale: Patient.gender = 'male'\n"
        "\n"
        "// # %% [name: MaleCount]\n"
        "define MaleCount: Count({IsMale})\n"
    )

    def test_cell_deps_composes_collection_literal_closure(self, server, ws):
        ws.send({"kind": "run", "library": "Demo", "cell": "MaleCount",
                 "mode": "cell_deps", "text": self._LIB})
        msg = ws.until({"result", "cellerror", "runerror"})
        assert msg is not None and msg["kind"] == "result"
        assert set(msg["cells"]) == {"IsMale", "MaleCount"}
        rows = msg["per_cell"]["MaleCount"]["rows"]
        assert all(r["MaleCount"] == 1 for r in rows)
        ismale = msg["per_cell"]["IsMale"]["rows"]
        assert sorted(bool(r["IsMale"]) for r in ismale) == [False, True]
