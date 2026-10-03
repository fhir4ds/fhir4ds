"""HTTP API: thin routes over the operations layer (single-user, 127.0.0.1)."""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from fhir4ds.operations.envelopes import LibraryText, tests_input_from_dict

from .cells import (
    CellRecord,
    CellSessionRegistry,
    ERROR,
    OK,
    RUNNING,
)
from .kernel import KernelManager
from .watcher import Watcher


def _envelope(ok: bool = True, **payload: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"schema": 1, "ok": ok}
    out.update(payload)
    return out


def _diag(message: str, code: str = "INPUT_ERROR") -> dict[str, Any]:
    return {"code": code, "message": message}


def _first_message(envelope: dict[str, Any]) -> str:
    diags = envelope.get("diagnostics") or []
    if diags and isinstance(diags[0], dict):
        return str(diags[0].get("message") or diags[0].get("code") or "evaluation failed")
    return "evaluation failed"


class DevHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying the dev-server state."""

    kernel_manager: KernelManager
    watcher: Watcher
    static_root: str = ""
    cell_registry: "CellSessionRegistry" = None  # type: ignore[assignment]


def create_server(
    kernel_manager: KernelManager,
    watcher: Watcher,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> DevHTTPServer:
    server = DevHTTPServer((host, port), _Handler)
    server.kernel_manager = kernel_manager
    server.watcher = watcher
    server.cell_registry = CellSessionRegistry()
    return server


def _library_texts(raw_list: Any) -> list[LibraryText]:
    if not isinstance(raw_list, list):
        raise ValueError("libraries must be an array of {name, text}")
    out: list[LibraryText] = []
    for item in raw_list:
        if not isinstance(item, dict) or "name" not in item or "text" not in item:
            raise ValueError("each library must be an object with name and text")
        out.append(LibraryText(name=item["name"], text=item["text"]))
    return out


class _Handler(BaseHTTPRequestHandler):
    server: DevHTTPServer

    # -- plumbing ----------------------------------------------------------

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 10_000_000:
            raise ValueError("request body too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def log_message(self, fmt: str, *args: Any) -> None:  # silence stderr noise
        pass

    # -- GET ---------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            kernel = self.server.kernel_manager.current()
            self._write_json(
                200,
                _envelope(
                    status="ok",
                    version=_version(),
                    kernel_id=kernel.kernel_id,
                    watching=len(self.server.watcher.files),
                    load_diagnostics=kernel.load_diagnostics,
                ),
            )
            return
        if path == "/api/events":
            self._websocket_events()
            return
        if path == "/api/workspace":
            snap = self.server.watcher.snapshot
            self._write_json(200, _envelope(workspace=snap.to_dict()))
            return
        if path == "/api/libraries":
            snap = self.server.watcher.snapshot
            self._write_json(200, _envelope(workspace=snap.to_dict()))
            return
        if path.startswith("/api/libraries/"):
            name = path[len("/api/libraries/"):]
            snap = self.server.watcher.snapshot
            lib = snap.library(name)
            if lib is None:
                self._write_json(
                    200, _envelope(ok=False, diagnostics=[_diag(f"library {name!r} not found", "NOT_FOUND")])
                )
                return
            self._write_json(
                200,
                _envelope(
                    name=lib.name,
                    path=str(lib.path),
                    parse_ok=lib.parse_ok,
                    error=lib.error,
                    definitions=list(lib.definitions),
                    text=lib.text,
                ),
            )
            return
        if path == "/api/fhirpath":
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            expr = (qs.get("expr") or [""])[0]
            resource_raw = (qs.get("resource") or [""])[0]
            try:
                resource = json.loads(resource_raw) if resource_raw else None
            except json.JSONDecodeError as exc:
                self._write_json(
                    200, _envelope(ok=False, diagnostics=[_diag(f"resource: {exc}")])
                )
                return
            from fhir4ds.operations import fhirpath_eval

            result = fhirpath_eval(expr, resource or {})
            self._write_json(200, result.to_dict())
            return
        if self._serve_static(path):
            return
        self._write_json(404, _envelope(ok=False, diagnostics=[_diag("not found", "NOT_FOUND")]))

    # -- POST --------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            body = self._read_json()
            if not isinstance(body, dict):
                raise ValueError("request body must be a JSON object")
        except ValueError as exc:
            self._write_json(400, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return

        try:
            if path == "/api/translate":
                self._route_translate(body)
            elif path == "/api/evaluate":
                self._route_evaluate(body)
            elif path == "/api/verify":
                self._route_verify(body)
            elif path == "/api/explain":
                self._route_explain(body)
            elif path == "/api/kernel/restart":
                snap = self.server.watcher.snapshot
                kernel = self.server.kernel_manager.restart(snap)
                # Cell results evaluated against the OLD kernel are stale.
                self.server.cell_registry.mark_stale_all()
                self._write_json(
                    200,
                    _envelope(
                        status="restarted",
                        kernel_id=kernel.kernel_id,
                        load_diagnostics=kernel.load_diagnostics,
                    ),
                )
            else:
                self._write_json(404, _envelope(ok=False, diagnostics=[_diag("not found", "NOT_FOUND")]))
        except (ValueError, TypeError) as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
        except KeyError as exc:
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[_diag(f"library {exc.args[0]!r} not found", "NOT_FOUND")],
                ),
            )

    # -- routes -------------------------------------------------------------

    def _resolve_main(self, body: dict[str, Any]) -> tuple[list[LibraryText], LibraryText]:
        """Build (includes, main) from explicit inline libraries or the workspace."""
        snap = self.server.watcher.snapshot
        if "libraries" in body:
            libs = _library_texts(body["libraries"])
            main_name = body.get("library") or (libs[-1].name if libs else "")
            main = next((l for l in libs if l.name == main_name), None)
            if main is None:
                raise ValueError(f"library {main_name!r} not in libraries")
            return [l for l in libs if l.name != main_name], main
        name = body.get("library") or ""
        if not name:
            raise ValueError("library is required")
        kernel = self.server.kernel_manager.current()
        return kernel.libraries_for(snap, name)

    def _route_translate(self, body: dict[str, Any]) -> None:
        includes, main = self._resolve_main(body)
        kernel = self.server.kernel_manager.current()
        payload = kernel.translate(
            includes, main, emit_sql=bool(body.get("emit_sql", True))
        )
        self._write_json(200, payload)

    def _route_evaluate(self, body: dict[str, Any]) -> None:
        includes, main = self._resolve_main(body)
        kernel = self.server.kernel_manager.current()
        # Per-define v1: `evaluate_library` returns every definition column;
        # narrowing output_columns to a single define projects the SQL to
        # that column only — same engine seam, no new capability. The full
        # result (all defines) is returned when `define` is absent.
        output_columns = body.get("output_columns")
        define = body.get("define")
        if define is not None:
            if not isinstance(define, str) or not define:
                raise ValueError("define must be a non-empty string")
            output_columns = {define: define}
        payload = kernel.evaluate(
            includes,
            main,
            parameters=body.get("parameters"),
            output_columns=output_columns,
        )
        self._write_json(200, payload)

    def _route_verify(self, body: dict[str, Any]) -> None:
        includes, main = self._resolve_main(body)
        try:
            cases = tests_input_from_dict({"cases": body.get("cases", [])})
        except (TypeError, ValueError) as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        kernel = self.server.kernel_manager.current()
        payload = kernel.verify(includes, main, cases)
        self._write_json(200, payload)

    def _route_explain(self, body: dict[str, Any]) -> None:
        includes, main = self._resolve_main(body)
        patient = body.get("patient_id") or body.get("patient")
        if not isinstance(patient, str) or not patient:
            raise ValueError("patient_id is required")
        kernel = self.server.kernel_manager.current()
        payload = kernel.explain(includes, main, patient)
        self._write_json(200, payload)

    # -- static UI ----------------------------------------------------------

    def _serve_static(self, path: str) -> bool:
        """Serve the committed built UI from fhir4ds/devserver/static."""
        import mimetypes
        from pathlib import Path

        static_root = Path(__file__).resolve().parent / "static"
        if path == "/":
            candidate = static_root / "index.html"
        elif path.startswith("/assets/"):
            rel = path[len("/assets/"):]
            if "/" in rel or ".." in rel:
                return False
            candidate = static_root / "assets" / rel
        else:
            return False
        if not candidate.is_file():
            return False
        ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    # -- WebSocket events channel (RFC 6455, stdlib-only) -------------------
    #
    # Server->client events over a minimal stdlib WebSocket (conductor
    # ruling 2026-10-03: WebSockets instead of SSE; no dual transport).
    # v1 pushes events only; client text frames are read and ignored
    # (the socket is future-proofed for v2 bidirectional commands).

    def _websocket_events(self) -> None:
        from . import ws as ws_protocol

        key = self.headers.get("Sec-WebSocket-Key")
        upgrade = (self.headers.get("Upgrade") or "").lower()
        if key is None or "websocket" not in upgrade:
            self._write_json(
                400, _envelope(ok=False, diagnostics=[_diag("websocket upgrade required")])
            )
            return
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", ws_protocol.accept_key(key))
        self.end_headers()

        q = self.server.watcher.bus.subscribe()
        conn_id = id(self.connection)
        run_queue: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=1)

        def on_client_message(payload: str) -> None:
            """Dispatch client->server commands (v2 cells protocol)."""
            try:
                msg = json.loads(payload)
            except ValueError:
                return
            if not isinstance(msg, dict):
                return
            if msg.get("kind") == "run":
                # Conductor ruling 2: cap-1 latest-wins queue.
                try:
                    run_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    run_queue.put_nowait(msg)
                except queue.Full:
                    pass
            elif msg.get("kind") == "sync":
                session = self.server.cell_registry.get(conn_id, str(msg.get("library") or ""))
                session.sync(str(msg.get("text") or ""))

        def reader() -> None:
            """Reader thread: consumes client frames until EOF/close."""
            try:
                while True:
                    opcode, payload = ws_protocol.read_client_frame(self.rfile)
                    if opcode == ws_protocol.OP_CLOSE:
                        return
                    if opcode == ws_protocol.OP_PING:
                        try:
                            self.wfile.write(ws_protocol.encode_pong_frame(payload))
                            self.wfile.flush()
                        except Exception:
                            return
                    elif opcode == ws_protocol.OP_TEXT:
                        on_client_message(payload.decode("utf-8", "replace"))
            except Exception:
                return

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()
        try:
            # Connected frame doubles as the subscription barrier: clients
            # that publish after consuming it are guaranteed delivery.
            self.wfile.write(ws_protocol.encode_text_frame('{"kind":"connected"}'))
            self.wfile.flush()
            while True:
                # Drain at most one pending run between event polls; runs
                # execute inline on this socket thread (single-user).
                try:
                    run_msg = run_queue.get_nowait()
                except queue.Empty:
                    run_msg = None
                if run_msg is not None:
                    self._execute_cell_run(conn_id, run_msg)
                    continue
                try:
                    event = q.get(timeout=0.5)
                except queue.Empty:
                    # Keepalive ping; a dead client surfaces as WsEOF on
                    # the read side or a broken-pipe write below.
                    idle_ticks = getattr(self, "_idle_ticks", 0) + 1
                    self._idle_ticks = idle_ticks
                    if idle_ticks >= 30:  # ~15s of idleness -> keepalive
                        self._idle_ticks = 0
                        self.wfile.write(ws_protocol.encode_text_frame('{"kind":"ping"}'))
                        self.wfile.flush()
                    continue
                self._idle_ticks = 0
                self.wfile.write(
                    ws_protocol.encode_text_frame(ws_protocol.event_json(event))
                )
                self.wfile.flush()
        except Exception:  # client disconnected (WsEOF / broken pipe)
            pass
        finally:
            self.server.watcher.bus.unsubscribe(q)
            self.server.cell_registry.drop(conn_id)
            reader_thread.join(timeout=2)
            try:
                self.wfile.write(ws_protocol.encode_close_frame())
                self.wfile.flush()
            except Exception:
                pass

    def _ws_send(self, obj: dict[str, Any]) -> None:
        from . import ws as ws_protocol

        self.wfile.write(ws_protocol.encode_text_frame(json.dumps(obj)))
        self.wfile.flush()

    def _execute_cell_run(self, conn_id: int, msg: dict[str, Any]) -> None:
        """Execute one v2 cell run request and push per-cell results."""
        library = str(msg.get("library") or "")
        cell = str(msg.get("cell") or "")
        mode = str(msg.get("mode") or "cell")
        text = msg.get("text")
        if not library or not cell:
            self._ws_send({"kind": "runerror", "message": "library and cell are required"})
            return
        session = self.server.cell_registry.get(conn_id, library)
        if isinstance(text, str) and text:
            session.sync(text)

        run_seq = session.next_run_seq()
        try:
            names = session.plan(cell, mode)
        except KeyError:
            self._ws_send({"kind": "runerror", "message": f"unknown cell {cell!r}"})
            return
        except ValueError as exc:
            self._ws_send({"kind": "runerror", "message": str(exc)})
            return

        # Recompute the refs-based selection for split attribution (the
        # plan may be file-order based for all/to_here modes; the split
        # narrows per-cell columns regardless of composition order).
        for name in names:
            session.set_result(name, CellRecord(status=RUNNING, run_seq=run_seq))
        self._ws_send(
            {
                "kind": "cellstate",
                "library": library,
                "run_seq": run_seq,
                "states": {n: RUNNING for n in names},
            }
        )

        composed = session.compose(names)
        includes, main = self._cell_libraries(library, composed)
        kernel = self.server.kernel_manager.current()
        envelope = kernel.evaluate(
            includes,
            main,
            output_columns={n: n for n in names},
        )

        if not envelope.get("ok"):
            # Whole-composition failure: attribute to the REQUESTING cell
            # only (review-note test pins this for mid-split errors).
            for name in names:
                rec = session.get_result(name) or CellRecord()
                rec.status = ERROR
                rec.error = _first_message(envelope)
                rec.run_seq = run_seq
                session.set_result(name, rec)
            self._ws_send(
                {
                    "kind": "cellerror",
                    "library": library,
                    "cell": cell,
                    "run_seq": run_seq,
                    "cells": names,
                    "diagnostics": envelope.get("diagnostics", []),
                }
            )
            return

        columns = envelope.get("columns", [])
        rows = envelope.get("rows", [])
        for name in names:
            if name not in columns:
                # Cell contributed no column (e.g. function cell): keep
                # idle-with-note rather than fabricated results.
                rec = session.get_result(name) or CellRecord()
                rec.status = OK
                rec.run_seq = run_seq
                session.set_result(name, rec)
                continue
            rec = session.get_result(name) or CellRecord()
            rec.status = OK
            rec.run_seq = run_seq
            rec.result = {
                "column_types": {name: envelope.get("column_types", {}).get(name)},
                "rows": [{name: row.get(name)} for row in rows],
                "patient_count": envelope.get("patient_count", 0),
                "sql": envelope.get("sql"),
            }
            session.set_result(name, rec)
        self._ws_send(
            {
                "kind": "result",
                "library": library,
                "cell": cell,
                "run_seq": run_seq,
                "cells": names,
                "sql": envelope.get("sql"),
                "per_cell": {
                    n: session.get_result(n).result for n in names if session.get_result(n)
                },
                "states": {n: OK for n in names},
            }
        )

    def _cell_libraries(
        self, library_name: str, composed_text: str
    ) -> tuple[list[LibraryText], LibraryText]:
        """Includes from the workspace snapshot + composed main inline."""
        snap = self.server.watcher.snapshot
        includes: list[LibraryText] = []
        for lib in snap.libraries:
            if lib.name != library_name:
                includes.append(lib.library_text())
        return includes, LibraryText(name=library_name, text=composed_text)


def _version() -> str:
    try:
        import fhir4ds

        return fhir4ds.__version__
    except Exception:  # pragma: no cover
        return "?"


def run_dev_server(cfg: Any) -> None:
    """Build and run the dev server (blocking; CLI entry point)."""
    from .discovery import scan_workspace

    snapshot = scan_workspace(cfg)
    manager = KernelManager(snapshot)
    manager.port = cfg.port
    from .watcher import EventBus

    bus = EventBus()
    watcher = Watcher(cfg, bus)
    watcher.start()
    server = create_server(manager, watcher, host=cfg.host, port=cfg.port)
    host, port = server.server_address[:2]
    print(f"fhir4ds dev server listening on http://{host}:{port}")  # noqa: T201
    print(f"workspace: {cfg.root}")  # noqa: T201
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        server.server_close()
