"""HTTP API: thin routes over the operations layer (single-user, 127.0.0.1)."""

from __future__ import annotations

import json
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from fhir4ds.operations.envelopes import LibraryText, tests_input_from_dict

from .kernel import KernelManager
from .watcher import Watcher


def _envelope(ok: bool = True, **payload: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"schema": 1, "ok": ok}
    out.update(payload)
    return out


def _diag(message: str, code: str = "INPUT_ERROR") -> dict[str, Any]:
    return {"code": code, "message": message}


class DevHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying the dev-server state."""

    kernel_manager: KernelManager
    watcher: Watcher
    static_root: str = ""


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
            self._sse()
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

    # -- SSE ----------------------------------------------------------------

    def _sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        q = self.server.watcher.bus.subscribe()
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(event.sse().encode("utf-8"))
                self.wfile.flush()
        except Exception:  # client disconnected
            pass
        finally:
            self.server.watcher.bus.unsubscribe(q)


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
