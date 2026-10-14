"""HTTP API: thin routes over the operations layer (single-user, 127.0.0.1)."""

from __future__ import annotations

import datetime
import json
import os
import queue
import re
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from fhir4ds.operations.envelopes import LibraryText, tests_input_from_dict
from fhir4ds.operations.errors import OperationError
from fhir4ds.operations.capabilities.evaluate import evaluate_library
from fhir4ds.operations.capabilities.measure import (
    flatten_view,
    measure_from_definitions,
    measure_report_from_rows,
    output_columns_from_measure,
)

from .expected_store import (
    IS_TEST_CASES_URL as IS_TEST_CASES_URL_CONST,
    build_expected_report,
    delete_expected_report,
    is_test_case_report,
    load_expected_reports,
    parse_expected_groups,
    patient_from_report,
    save_expected_report,
)
from .cells import (
    CellRecord,
    CellSessionRegistry,
    ERROR,
    OK,
    RUNNING,
)
from .kernel import KernelManager
from .watcher import Watcher, WorkspaceEvent


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


def _regroup_report_populations(report: dict[str, Any]) -> dict[str, Any]:
    """Merge per-code group entries into one entry per group id.

    The operations layer emits one MeasureReport.group entry per
    population code (S-1 dual representation). The dev-server UI
    normalizes to the Measure's own grouping: one group entry per
    group id containing all its populations, order preserved.
    """
    merged: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for entry in report.get("group") or []:
        gid = entry.get("id") if isinstance(entry, dict) else None
        if gid is None:
            merged.append(entry)
            continue
        bucket = by_id.get(gid)
        if bucket is None:
            bucket = {"id": gid, "population": []}
            by_id[gid] = bucket
            merged.append(bucket)
        for pop in entry.get("population") or []:
            bucket["population"].append(pop)
    report["group"] = merged
    return report


class DevHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying the dev-server state."""

    kernel_manager: KernelManager
    watcher: Watcher
    static_root: str = ""
    cell_registry: "CellSessionRegistry" = None  # type: ignore[assignment]
    valuesets_stale: bool = False
    # parity item 2: CURRENT sql store (sha -> text) for copy-sql-ref;
    # stale shas honestly report 'sql superseded'.
    sql_store: dict[str, str] = {}


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _valueset_stem_from_url(url: str) -> str:
    """File-stem for an imported canonical: OID tail or last URL segment."""
    tail = url.rstrip("|").rstrip("/").rsplit("/", 1)[-1]
    tail = tail.split("|")[0] or "valueset"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in tail)
    return safe or "valueset"


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
    # v3 Slice 1: set True when a valueset edit was written to disk but the
    # kernel still holds the terminology loaded at startup (restart reloads).
    server.valuesets_stale = False
    # c-vsac-cleanroom: terminology connectivity (lazy — endpoint built on
    # first use; API key resolved at call time, never stored/logged).
    from .config import terminology_settings

    server.terminology_settings = terminology_settings(watcher._cfg)
    server._terminology_endpoint_holder = None
    server._umls_endpoint_holder = None
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

    # -- terminology connectivity (c-vsac-cleanroom) -----------------------

    def _publish_changed(self, paths: list[str]) -> None:
        """Publish a workspace 'changed' event on the watcher bus."""
        self.server.watcher.bus.publish(
            WorkspaceEvent(kind="changed", paths=paths)
        )

    def _terminology_status(self) -> dict[str, Any]:
        """Status payload for /health: provider + configured flag.

        NEVER includes key material — only whether the API key env var is
        SET (presence check, not the value).
        """
        settings = getattr(self.server, "terminology_settings", None)
        if settings is None:
            return {"provider": "disabled", "configured": False}
        return {
            "provider": settings.provider,
            "configured": settings.provider != "disabled",
            "api_key_set": bool(settings.api_key()),
        }

    def _terminology_endpoint(self):
        """Lazily build the VCACTerminologyEndpoint (vsac or generic http
        base URL). Returns None when the provider is disabled."""
        if self.server._terminology_endpoint_holder is None:
            settings = self.server.terminology_settings
            if settings.provider == "disabled":
                return None
            from fhir4ds.cql.terminology.vsac_adapter import (
                VCACTerminologyEndpoint,
            )

            self.server._terminology_endpoint_holder = VCACTerminologyEndpoint(
                base_url=settings.base_url or "https://cts.nlm.nih.gov/fhir",
                timeout_seconds=settings.timeout_seconds,
                api_key=settings.api_key(),
            )
        return self.server._terminology_endpoint_holder

    def _umls_endpoint(self):
        """Lazily build the UMLSTerminologyEndpoint for code search.

        Independent of the [terminology] provider (available whenever a
        UMLS key resolves) — UTS REST auth differs from the VSAC FHIR
        endpoint, so it gets its own lazy holder. Returns None when no
        key is configured."""
        if self.server._umls_endpoint_holder is None:
            settings = self.server.terminology_settings
            key = settings.api_key() if settings else None
            if not key:
                import os

                key = os.environ.get("FHIR4DS_UMLS_API_KEY")
            if not key:
                return None
            from fhir4ds.cql.terminology.umls_adapter import (
                UMLSTerminologyEndpoint,
            )

            self.server._umls_endpoint_holder = UMLSTerminologyEndpoint(
                timeout_seconds=settings.timeout_seconds if settings else 15.0,
                api_key=key,
            )
        return self.server._umls_endpoint_holder

    def _route_terminology_search(self, body: dict[str, Any]) -> None:
        """POST /api/terminology/search — UMLS code lookup by concept
        name (c-umls-lookup). Results are display-only; adding a code to
        a valueset goes through the existing /api/valueset/edit."""
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            self._write_json(
                200, _envelope(ok=False, diagnostics=[_diag("query is required")])
            )
            return
        system = body.get("system")
        if system is not None and not isinstance(system, str):
            self._write_json(
                200,
                _envelope(ok=False, diagnostics=[_diag("system must be a string")]),
            )
            return
        endpoint = self._umls_endpoint()
        if endpoint is None:
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[
                        _diag(
                            "UMLS API key not configured — set UMLS_API_KEY "
                            "or [terminology] api_key_env in fhir4ds.toml"
                        )
                    ],
                ),
            )
            return
        try:
            results = endpoint.search_text(query.strip(), system or None)
        except Exception as exc:  # adapter errors carry no key material
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        payload = [
            {
                "system": r.system,
                "code": r.code,
                "display": r.display,
            }
            for r in results
        ]
        self._write_json(
            200, _envelope(ok=True, query=query.strip(), results=payload, count=len(payload))
        )

    def _route_terminology_config_get(self) -> None:
        """GET /api/terminology/config — current settings + key-presence flag.

        The key VALUE never appears; ``key_env_resolves`` reports only
        whether the named env var is set in the server process.
        """
        import os

        s = self.server.terminology_settings
        self._write_json(
            200,
            _envelope(
                ok=True,
                config={
                    "provider": s.provider,
                    "base_url": s.base_url,
                    "timeout_seconds": s.timeout_seconds,
                    "api_key_env": s.api_key_env,
                    "key_env_resolves": bool(os.environ.get(s.api_key_env)),
                },
            ),
        )

    def _route_terminology_config_post(self, body: dict[str, Any]) -> None:
        """POST /api/terminology/config — persist [terminology] to fhir4ds.toml.

        Item-1 hard rule: only the env var NAME is accepted; a raw key
        value in any field is rejected outright (never written, never
        echoed beyond the rejection message).
        """
        from .config import DevConfigError, TerminologySettings, terminology_settings
        from .toml_writer import write_section

        if not isinstance(body, dict):
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag("body must be an object")]))
            return
        updates: dict[str, object] = {}
        allowed = {"provider", "base_url", "timeout_seconds", "api_key_env"}
        for key in allowed:
            if key in body:
                updates[key] = body[key]
        # Validate via the parse-side shapes BEFORE writing anything.
        try:
            candidate = TerminologySettings(
                provider=updates.get("provider", "vsac") if "provider" in updates else "vsac",
                **{k: v for k, v in updates.items() if k != "provider"},
            )
            if "provider" in updates and candidate.provider not in ("vsac", "http", "disabled"):
                raise DevConfigError(
                    f"provider must be one of ['disabled', 'http', 'vsac']; got {updates['provider']!r}"
                )
            if "base_url" in updates and (
                not isinstance(updates["base_url"], str) or not updates["base_url"].strip()
            ):
                raise DevConfigError("base_url must be a non-empty string")
            if "timeout_seconds" in updates and (
                not isinstance(updates["timeout_seconds"], (int, float))
                or not updates["timeout_seconds"] > 0
            ):
                raise DevConfigError("timeout_seconds must be a positive number")
            if "api_key_env" in updates and (
                not isinstance(updates["api_key_env"], str) or not updates["api_key_env"].strip()
            ):
                raise DevConfigError("api_key_env must be a non-empty string")
        except TypeError as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        except DevConfigError as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        cfg = getattr(self.server.watcher, "_cfg", None)
        if cfg is None:
            self._write_json(
                200, _envelope(ok=False, diagnostics=[_diag("workspace config unavailable")])
            )
            return
        toml_path = cfg.root / "fhir4ds.toml"
        try:
            write_section(toml_path, "terminology", updates)
            # Re-resolve settings + reset the lazy endpoint holders so the
            # next call uses the new config without a server restart.
            self.server.terminology_settings = terminology_settings(cfg)
            self.server._terminology_endpoint_holder = None
            self.server._umls_endpoint_holder = None
        except (OSError, ValueError) as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        s = self.server.terminology_settings
        self._write_json(
            200,
            _envelope(ok=True, config={"provider": s.provider, "base_url": s.base_url,
                                       "timeout_seconds": s.timeout_seconds,
                                       "api_key_env": s.api_key_env}),
        )

    def _route_fs_list(self) -> None:
        """GET /api/fs/list?path=... — server-side directory listing for pickers.

        Sandboxed to the workspace root and below; ``..`` and absolute
        paths outside root are rejected. Hidden entries are skipped.
        """
        from urllib.parse import parse_qs, urlparse

        cfg = getattr(self.server.watcher, "_cfg", None)
        if cfg is None:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag("workspace config unavailable")]))
            return
        query = parse_qs(urlparse(self.path).query)
        raw = (query.get("path") or [""])[0]
        root = cfg.root.resolve()
        target = root if not raw else (root / raw).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[_diag(f"path escapes the workspace root: {raw}")],
                ),
            )
            return
        if not target.is_dir():
            self._write_json(
                200, _envelope(ok=False, diagnostics=[_diag(f"not a directory: {raw or '.'}")])
            )
            return
        entries = []
        try:
            for child in sorted(target.iterdir()):
                name = child.name
                if name.startswith("."):
                    continue
                entries.append(
                    {
                        "name": name,
                        "kind": "dir" if child.is_dir() else "file",
                        "suffix": child.suffix.lower() if child.is_file() else "",
                    }
                )
        except OSError as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        rel = str(target.relative_to(root)) or "."
        self._write_json(200, _envelope(ok=True, path=rel, entries=entries))

    def _route_workspace_add_path(self, body: dict[str, Any]) -> None:
        """POST /api/workspace/add-path — persist a source path to [dev].

        Body: {kind: cql|valueset|measure|data|view, path}. Appends the
        entry to the matching [dev] array in fhir4ds.toml (manifest ADDS
        to convention; duplicates deduped at load), then rescans and
        restarts the watcher poll cycle so the new files surface.
        """
        from .config import _LIST_FIELDS  # key -> kind map

        kind = body.get("kind")
        path = body.get("path")
        kinds = {"cql", "valueset", "measure", "data", "view"}
        if kind not in kinds:
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[_diag(f"kind must be one of {sorted(kinds)}; got {kind!r}")],
                ),
            )
            return
        if not isinstance(path, str) or not path.strip():
            self._write_json(
                200, _envelope(ok=False, diagnostics=[_diag("path is required")])
            )
            return
        cfg = getattr(self.server.watcher, "_cfg", None)
        if cfg is None:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag("workspace config unavailable")]))
            return
        raw = path.strip()
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = cfg.root / candidate
        candidate = candidate.resolve()
        if not candidate.exists():
            self._write_json(
                200,
                _envelope(ok=False, diagnostics=[_diag(f"path does not exist: {raw}")]),
            )
            return
        # _LIST_FIELDS maps the TOML key (cql_dirs/data_dirs/...) -> kind;
        # the manifest arrays use the SAME _dirs-suffixed keys.
        key = next(k for k, v in _LIST_FIELDS.items() if v == kind)
        toml_path = cfg.root / "fhir4ds.toml"
        try:
            # Re-read manifest and append, preserving the other entries.
            from .config import _parse_manifest

            current = _parse_manifest(toml_path).get(key, [])
            rel = str(candidate)
            try:
                rel = str(candidate.relative_to(cfg.root.resolve()))
            except ValueError:
                pass
            if rel not in current:
                current.append(rel)
            from .toml_writer import write_section

            write_section(toml_path, "dev", {key: current})
            # Reload config so the watcher/kernel see the new path list
            # (the Watcher captured DevServerConfig at construction).
            from .config import load_config as _load_config

            new_cfg = _load_config(cfg.root)
            self.server.watcher._cfg = new_cfg
        except (OSError, ValueError) as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        snap = self.server.watcher.rescan()
        self._write_json(
            200,
            _envelope(ok=True, kind=kind, added=rel, snapshot={"datasets": len(snap.datasets),
                                                               "libraries": len(snap.libraries)}),
        )

    def _route_terminology_preview(self, body: dict[str, Any]) -> None:
        """POST /api/terminology/preview — expand a canonical URL/OID via
        the configured endpoint; concept preview only, no disk writes."""
        url = body.get("url")
        if not isinstance(url, str) or not url.strip():
            self._write_json(
                200, _envelope(ok=False, diagnostics=[_diag("url is required")])
            )
            return
        endpoint = self._terminology_endpoint()
        if endpoint is None:
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[
                        _diag(
                            "terminology provider is disabled — set "
                            "[terminology] in fhir4ds.toml or "
                            "FHIR4DS_TERMINOLOGY_PROVIDER"
                        )
                    ],
                ),
            )
            return
        try:
            codes = endpoint.expand(url.strip())
        except Exception as exc:  # adapter errors carry no key material
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        concepts = [
            {"system": c.system, "code": c.code, "display": c.display}
            for c in codes
        ]
        self._write_json(
            200, _envelope(url=url.strip(), concepts=concepts, count=len(concepts))
        )

    def _route_terminology_import(self, body: dict[str, Any]) -> None:
        """POST /api/terminology/import — expand + WRITE a local valueset
        file (origin+version provenance). Imported sets are ordinary local
        files from then on (normal stale/restart contract)."""
        url = body.get("url")
        name = body.get("name")
        if not isinstance(url, str) or not url.strip():
            self._write_json(
                200, _envelope(ok=False, diagnostics=[_diag("url is required")])
            )
            return
        if name is not None and (
            not isinstance(name, str)
            or not name
            or not all(ch.isalnum() or ch in "-_" for ch in name)
        ):
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[
                        _diag(
                            "name must be a non-empty identifier (alphanumerics, -, _)"
                        )
                    ],
                ),
            )
            return
        endpoint = self._terminology_endpoint()
        if endpoint is None:
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[
                        _diag(
                            "terminology provider is disabled — set "
                            "[terminology] in fhir4ds.toml or "
                            "FHIR4DS_TERMINOLOGY_PROVIDER"
                        )
                    ],
                ),
            )
            return
        try:
            codes = endpoint.expand(url.strip())
        except Exception as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        if not codes:
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[_diag(f"expansion of {url!r} returned no codes")],
                ),
            )
            return
        stem = name or _valueset_stem_from_url(url)
        snap = self.server.watcher.snapshot
        if snap.valuesets:
            vs_dir = Path(str(snap.valuesets[0])).parent
        else:
            cfg = getattr(self.server.watcher, "_cfg", None)
            vs_dir = (
                cfg.valueset_dirs[0]
                if cfg.valueset_dirs
                else cfg.root / "valuesets"
            )
        vs_dir.mkdir(parents=True, exist_ok=True)
        target = vs_dir / f"{stem}.json"
        n = 1
        while target.exists():
            target = vs_dir / f"{stem}-{n}.json"
            n += 1
        systems = sorted({c.system for c in codes})
        resource = {
            "resourceType": "ValueSet",
            "id": stem,
            "url": url.strip(),
            "name": stem,
            "status": "active",
            "compose": {
                "include": [
                    {
                        "system": system,
                        "concept": [
                            {"code": c.code, "display": c.display or ""}
                            for c in codes
                            if c.system == system
                        ],
                    }
                    for system in systems
                ]
            },
            "_origin": {
                "imported_from": url.strip(),
                "imported_at": _utc_now_iso(),
                "code_count": len(codes),
            },
        }
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(resource, fh, indent=2)
            fh.write("\n")
        self.server.valuesets_stale = True
        self._publish_changed([str(target)])
        self._write_json(
            200,
            _envelope(
                path=str(target), url=url.strip(), count=len(codes), stale=True
            ),
        )

    def _route_terminology_resolution(self) -> None:
        """GET /api/terminology/resolution — for each valueset declaration
        in every library, report where it resolves: local / VSAC / server /
        unresolved."""
        snap = self.server.watcher.snapshot
        local_urls: set[str] = set()
        for vp in snap.valuesets:
            try:
                with open(str(vp), "r", encoding="utf-8") as fh:
                    resource = json.load(fh)
                url = resource.get("url")
                if isinstance(url, str):
                    local_urls.add(url)
            except (OSError, json.JSONDecodeError):
                continue
        settings = getattr(self.server, "terminology_settings", None)
        provider = settings.provider if settings else "disabled"
        resolutions: list[dict[str, Any]] = []
        for lib in snap.libraries:
            for m in re.finditer(
                r"^[ \t]*valueset[ \t]+\"([^\"]+)\"[ \t]*:[ \t]*'([^']+)'",
                lib.text or "",
                re.MULTILINE,
            ):
                vs_id, url = m.group(1), m.group(2)
                if url in local_urls:
                    where = "local"
                elif provider == "vsac":
                    where = "VSAC"
                elif provider == "http":
                    where = "server"
                else:
                    where = "unresolved"
                resolutions.append(
                    {"library": lib.name, "id": vs_id, "url": url, "resolved": where}
                )
        self._write_json(200, _envelope(resolutions=resolutions, provider=provider))

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
                    valuesets_stale=self.server.valuesets_stale,
                    terminology=self._terminology_status(),
                ),
            )
            return
        if path == "/api/events":
            self._websocket_events()
            return
        if path == "/api/boxes":
            # ux3: boxes projection for a library (spans + titles).
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            name = (qs.get("name") or [""])[0]
            snap = self.server.watcher.snapshot
            lib = next((l for l in snap.libraries if l.name == name), None)
            if lib is None:
                self._write_json(
                    200, _envelope(ok=False, diagnostics=[_diag(f"unknown library {name!r}")])
                )
                return
            from .cells import split_boxes

            boxes = [
                {
                    "title": b.title,
                    "title_source": b.title_source,
                    "kind": b.kind,
                    "name": b.name,
                    "start": b.start,
                    "end": b.end,
                }
                for b in split_boxes(lib.text or "")
            ]
            self._write_json(200, _envelope(library=name, boxes=boxes))
            return
        if path == "/api/dataset-stats":
            # ux3 Part B: real dataset detail — row count + resourceType mix.
            kernel = self.server.kernel_manager.current()
            try:
                rows = kernel.conn.execute(
                    "SELECT resource->>'resourceType' AS rt, COUNT(*) AS n"
                    " FROM resources GROUP BY 1 ORDER BY 2 DESC"
                ).fetchall()
                stats = [{"resourceType": r[0], "count": r[1]} for r in rows]
                self._write_json(200, _envelope(ok=True, total=sum(s["count"] for s in stats), by_type=stats))
            except Exception as exc:
                self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        if path == "/api/dataset":
            # v4.4: dataset file read — resource list + per-line parse errors.
            from urllib.parse import parse_qs, urlparse

            query = parse_qs(urlparse(self.path).query)
            dpath = (query.get("path") or [""])[0]
            snap = self.server.watcher.snapshot
            if dpath not in {str(p) for p in snap.datasets}:
                self._write_json(
                    200,
                    _envelope(
                        False,
                        diagnostics=[_diag(f"unknown dataset path: {dpath}")],
                    ),
                )
                return
            resources: list[dict[str, Any]] = []
            parse_errors: list[dict[str, Any]] = []
            try:
                with open(dpath, "r", encoding="utf-8-sig") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError as exc:
                            parse_errors.append({"line": lineno, "error": str(exc)})
                            continue
                        if isinstance(obj, dict):
                            resources.append(obj)
                        else:
                            parse_errors.append(
                                {"line": lineno, "error": "line is not a JSON object"}
                            )
            except OSError as exc:
                self._write_json(200, _envelope(False, diagnostics=[_diag(str(exc))]))
                return
            self._write_json(
                200,
                _envelope(path=dpath, resources=resources, parse_errors=parse_errors),
            )
            return
        if path == "/api/library-header":
            # v3 Slice 1: header info (library/includes/parameters) for the
            # Parameters pane.
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            name = (qs.get("library") or [""])[0]
            snap = self.server.watcher.snapshot
            lib = next((l for l in snap.libraries if l.name == name), None)
            if lib is None:
                self._write_json(
                    200, _envelope(ok=False, diagnostics=[_diag(f"unknown library {name!r}")])
                )
                return
            from .resources import header_info

            info = header_info(lib.text or "")
            self._write_json(200, _envelope(library=info["library"], includes=info["includes"], parameters=info["parameters"]))
            return
        if path == "/api/patients":
            # v3 Slice 1: distinct patient ids for the test-cases dropdown
            # (never free text). Dedup happens in Python: aggregate/DISTINCT
            # forms over `resources` intermittently bind wrong columns on
            # this shared conn (observed returning resourceType values), so
            # the route selects bare rows and dedupes/storts here.
            kernel = self.server.kernel_manager.current()
            try:
                rows = kernel.conn.execute(
                    "SELECT id, resourceType FROM resources"
                    " WHERE resourceType = 'Patient'"
                ).fetchall()
                ids = sorted({r[0] for r in rows if r[0] is not None and r[1] == "Patient"})
                self._write_json(200, _envelope(patients=ids))
            except Exception as exc:
                self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        if path == "/api/patient/resources":
            # S5 (item 7): one patient's resources grouped by resourceType
            # (patient slide-out). Uses the loader-maintained patient_ref
            # column; Patient rows themselves carry their own id.
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            pid = (qs.get("id") or [""])[0].strip()
            if not pid:
                self._write_json(
                    200, _envelope(ok=False, diagnostics=[_diag("id is required")])
                )
                return
            kernel = self.server.kernel_manager.current()
            try:
                full_type = (qs.get("resourceType") or [""])[0].strip()
                full_rid = (qs.get("rid") or [""])[0].strip()
                if full_type and full_rid:
                    # Muse fix: full-resource fetch for the builder handoff
                    # (previews are 200 chars and unparseable).
                    row = kernel.conn.execute(
                        "SELECT resource FROM resources"
                        " WHERE resourceType = ? AND id = ?",
                        [full_type, full_rid],
                    ).fetchone()
                    payload = None
                    if row and row[0] is not None:
                        try:
                            payload = (
                                row[0]
                                if isinstance(row[0], dict)
                                else json.loads(row[0])
                            )
                        except (ValueError, TypeError):
                            payload = None
                    self._write_json(
                        200,
                        _envelope(
                            patient=pid,
                            resource=payload,
                            ok=payload is not None,
                            diagnostics=None
                            if payload is not None
                            else [_diag(f"resource {full_type}/{full_rid} not found")],
                        ),
                    )
                    return
                rows = kernel.conn.execute(
                    "SELECT id, resourceType, resource, patient_ref FROM resources"
                    " WHERE id = ? OR patient_ref = ? ORDER BY resourceType, id",
                    [pid, pid],
                ).fetchall()
                by_type: dict[str, list[dict[str, Any]]] = {}
                for rid, rtype, resource, _pref in rows:
                    payload = resource if isinstance(resource, dict) else None
                    if payload is None:
                        try:
                            import json as _json

                            payload = _json.loads(resource) if resource else {}
                        except (ValueError, TypeError):
                            payload = {}
                    by_type.setdefault(str(rtype or "?"), []).append(
                        {
                            "id": rid,
                            "resourceType": rtype,
                            "status": payload.get("status"),
                            "date": payload.get("effectiveDateTime")
                            or payload.get("effectiveDate")
                            or payload.get("authoredOn")
                            or payload.get("birthDate"),
                            "preview": str(payload)[:200],
                        }
                    )
                self._write_json(
                    200,
                    _envelope(
                        patient=pid,
                        total=sum(len(v) for v in by_type.values()),
                        by_type=by_type,
                    ),
                )
            except Exception as exc:
                self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        if path == "/api/define-types":
            # v3 Slice-2 gate: translator-backed define classification for
            # the measure mapping dropdowns (boolean Patient-context defines
            # are the only valid population members). text= is the
            # client-authoritative buffer (run-with-text doctrine); absent
            # falls back to the workspace file.
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            name = (qs.get("library") or [""])[0]
            text = (qs.get("text") or [None])[0]
            snap = self.server.watcher.snapshot
            lib = next((l for l in snap.libraries if l.name == name), None)
            if lib is None:
                self._write_json(
                    200, _envelope(ok=False, diagnostics=[_diag(f"unknown library {name!r}")])
                )
                return
            if text is None:
                text = lib.text or ""
            try:
                from fhir4ds.cql.parser import parse_cql
                from fhir4ds.cql.translator.translator import CQLToSQLTranslator

                lib_ast = parse_cql(text)
                translator = CQLToSQLTranslator()
                translator.translate_library_to_population_sql(lib_ast)
                defines = []
                for stmt in getattr(lib_ast, "statements", []):
                    if type(stmt).__name__ != "Definition":
                        continue  # function defines carry no population result
                    stmt_name = getattr(stmt, "name", None)
                    if stmt_name is None:
                        continue
                    cql_type = None
                    try:
                        meta = translator.get_definition_meta(stmt_name)
                        if meta is not None:
                            cql_type = getattr(meta, "cql_type_ref", None) or getattr(
                                meta, "cql_type", None
                            )
                    except Exception:
                        cql_type = None
                    defines.append(
                        {
                            "name": stmt_name,
                            "cql_type": cql_type,
                            "boolean": cql_type == "Boolean",
                        }
                    )
                self._write_json(200, _envelope(library=name, defines=defines))
            except Exception as exc:
                # Incomplete/dangling libs fail translation: report all
                # defines as untyped so the UI can show them greyed out.
                try:
                    from fhir4ds.cql.parser import parse_cql as _parse

                    defines = []
                    lib_ast = _parse(text)
                    for stmt in getattr(lib_ast, "statements", []):
                        if type(stmt).__name__ != "Definition":
                            continue
                        stmt_name = getattr(stmt, "name", None)
                        if stmt_name is None:
                            continue
                        defines.append(
                            {"name": stmt_name, "cql_type": None, "boolean": False}
                        )
                    self._write_json(200, _envelope(library=name, defines=defines))
                except Exception:
                    self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        if path == "/api/valueset":
            # v3 Slice 1: valueset grid read (concepts + used-by + url).
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            vs_path = (qs.get("path") or [""])[0]
            snap = self.server.watcher.snapshot
            if vs_path not in [str(p) for p in snap.valuesets]:
                self._write_json(
                    200,
                    _envelope(ok=False, diagnostics=[_diag(f"unknown valueset path {vs_path!r}")]),
                )
                return
            try:
                with open(vs_path, "r", encoding="utf-8") as fh:
                    resource = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
                return
            from fhir4ds.cql.loader.fhir_loader import _extract_codes_from_valueset_resource
            from .resources import valueset_used_by

            concepts = _extract_codes_from_valueset_resource(resource) or []
            lib_pairs = [(l.name, l.text or "") for l in snap.libraries]
            self._write_json(
                200,
                _envelope(
                    path=vs_path,
                    url=resource.get("url"),
                    concepts=concepts,
                    used_by=valueset_used_by(resource, lib_pairs),
                    stale=self.server.valuesets_stale,
                ),
            )
            return
        if path == "/api/schema-tree":
            # v4.1 Resource Builder: schema-tree driven field assistance.
            from urllib.parse import parse_qs, urlparse

            from fhir4ds.operations.capabilities.schema_tree import resource_schema_tree

            qs = parse_qs(urlparse(self.path).query)
            resource_type = (qs.get("resource") or [""])[0]
            if not resource_type:
                self._write_json(
                    200,
                    _envelope(ok=False, diagnostics=[_diag("resource parameter is required")]),
                )
                return
            depth_raw = (qs.get("depth") or ["2"])[0]
            try:
                depth = max(1, min(int(depth_raw), 4))
            except ValueError:
                depth = 2
            try:
                result = resource_schema_tree(resource_type, depth=depth)
                payload = result.to_dict()
            except Exception as exc:
                self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
                return
            self._write_json(200, payload)
            return
        if path == "/api/measure/baselines":
            from pathlib import Path
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            measure_name = (qs.get("measure") or [""])[0].strip()
            snap = self.server.watcher.snapshot
            roots = [Path(str(d)).parent for d in (getattr(snap, "measures", None) or [])]
            if roots:
                expected_dir = roots[0] / "expected"
            else:
                cfg = getattr(self.server.watcher, "_cfg", None)
                data_dirs = list(getattr(cfg, "data_dirs", None) or [])
                expected_dir = (
                    Path(data_dirs[0]).parent / "measures" / "expected"
                    if data_dirs
                    else Path("measures") / "expected"
                )
            baselines: list[dict[str, Any]] = []
            if expected_dir.is_dir():
                for f in sorted(expected_dir.glob("*.baseline.v*.json")):
                    stem = f.name.split(".baseline.v")[0]
                    if measure_name and stem != measure_name:
                        continue
                    entry: dict[str, Any] = {"path": str(f), "name": f.name}
                    try:
                        with open(f, "r", encoding="utf-8") as fh:
                            wrapper = json.load(fh)
                        prov = wrapper.get("provenance") or {}
                        entry["provenance"] = prov
                        entry["reports"] = len(wrapper.get("reports") or [])
                    except (OSError, json.JSONDecodeError) as exc:
                        entry["error"] = str(exc)
                    baselines.append(entry)
            self._write_json(200, _envelope(baselines=baselines))
            return
        if path == "/api/measure/baseline/raw":
            from pathlib import Path
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            raw_path = (qs.get("path") or [""])[0]
            target = Path(raw_path).resolve()
            if target.parent.name != "expected" or not target.is_file():
                self._write_json(
                    200, _envelope(False, diagnostics=[_diag("unknown baseline path")])
                )
                return
            try:
                wrapper = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self._write_json(200, _envelope(False, diagnostics=[_diag(str(exc))]))
                return
            self._write_json(200, _envelope(wrapper=wrapper))
            return
        if path == "/api/terminology/resolution":
            self._route_terminology_resolution()
            return
        if path == "/api/terminology/config":
            self._route_terminology_config_get()
            return
        if path == "/api/fs/list":
            self._route_fs_list()
            return
        if path == "/api/runs/sql":
            from urllib.parse import parse_qs, urlparse

            from .runlog import _sha

            q = parse_qs(urlparse(self.path).query)
            sha = (q.get("sha") or [""])[0]
            text = self.server.sql_store.get(sha)
            if text is not None:
                self._write_json(200, _envelope(ok=True, sql=text))
            else:
                self._write_json(
                    200,
                    _envelope(
                        ok=False,
                        diagnostics=[_diag("sql superseded — rerun the target to regenerate it")],
                    ),
                )
        elif path == "/api/runs":
            # parity item 2: run history (newest-first; ?kind=&limit=)
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query)
            kind = (q.get("kind") or [""])[0] or None
            try:
                limit = int((q.get("limit") or ["200"])[0])
            except ValueError:
                limit = 200
            events = self._runlog().load(kind=kind, limit=limit)
            self._write_json(200, _envelope(ok=True, runs=events, count=len(events)))
        elif path == "/api/tests/expected":
            self._route_tests_expected_get()
            return
        if path == "/api/view":
            # v3 Slice 4: ViewDefinition file read (text + parsed header info).
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            v_path = (qs.get("path") or [""])[0]
            snap = self.server.watcher.snapshot
            if v_path not in [str(p) for p in snap.views]:
                self._write_json(
                    200,
                    _envelope(ok=False, diagnostics=[_diag(f"unknown view path {v_path!r}")]),
                )
                return
            try:
                with open(v_path, "r", encoding="utf-8") as fh:
                    text = fh.read()
                resource = json.loads(text)
                resource_type = resource.get("resource") if isinstance(resource, dict) else None
                name = resource.get("name") if isinstance(resource, dict) else None
            except (OSError, json.JSONDecodeError) as exc:
                self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
                return
            self._write_json(
                200,
                _envelope(path=v_path, text=text, resource=resource_type, name=name),
            )
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
            if path == "/api/rename-box":
                # ux3: rename a box title (label edit or define refactor).
                # Body: {library, title, new_title}. The server re-derives
                # the box from the CURRENT workspace file text; clients that
                # hold an edited buffer should sync first.
                from .cells import split_boxes

                lib_name = str(body.get("library") or "")
                snap = self.server.watcher.snapshot
                lib = next((l for l in snap.libraries if l.name == lib_name), None)
                if lib is None:
                    self._write_json(
                        200, _envelope(ok=False, diagnostics=[_diag(f"unknown library {lib_name!r}")])
                    )
                    return
                title = str(body.get("title") or "")
                new_title = str(body.get("new_title") or "")
                boxes = split_boxes(lib.text or "")
                box = next((b for b in boxes if b.title == title), None)
                if box is None:
                    self._write_json(
                        200, _envelope(ok=False, diagnostics=[_diag(f"unknown box {title!r}")])
                    )
                    return
                from .cells import rename_box

                try:
                    new_text = rename_box(lib.text or "", box, new_title)
                except ValueError as exc:
                    self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
                    return
                # In-memory session update (zero-write doctrine); the file
                # itself is only touched by the author's editor.
                session = self.server.cell_registry.get(id(self.connection), lib_name)
                session.sync(new_text)
                new_boxes = [
                    {
                        "title": b.title,
                        "title_source": b.title_source,
                        "kind": b.kind,
                        "name": b.name,
                        "start": b.start,
                        "end": b.end,
                    }
                    for b in split_boxes(new_text)
                ]
                self._write_json(
                    200, _envelope(ok=True, library=lib_name, text=new_text, boxes=new_boxes)
                )
                return
            if path == "/api/parameters":
                # v3 Slice 1: parameter upsert/delete. Returns the NEW text
                # (in-memory buffer doctrine — client splices; like rename-box,
                # the session is synced so subsequent runs see the change).
                from .resources import delete_parameter, upsert_parameter

                lib_name = str(body.get("library") or "")
                action = str(body.get("action") or "upsert")
                snap = self.server.watcher.snapshot
                lib = next((l for l in snap.libraries if l.name == lib_name), None)
                if lib is None:
                    self._write_json(
                        200, _envelope(ok=False, diagnostics=[_diag(f"unknown library {lib_name!r}")])
                    )
                    return
                name = body.get("name")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("name must be a non-empty string")
                # The edit loop is in-memory + Apply: when the client carries
                # an edited buffer it is authoritative; otherwise fall back to
                # the workspace file text. Edits are stateless transforms so
                # they compose client-side across sequential calls.
                text = body.get("text")
                if not isinstance(text, str):
                    text = lib.text or ""
                try:
                    if action == "delete":
                        new_text = delete_parameter(text, name)
                    elif action == "upsert":
                        ptype = body.get("type")
                        if not isinstance(ptype, str) or not ptype.strip():
                            raise ValueError("type must be a non-empty string")
                        default = body.get("default")  # optional raw CQL expr text
                        if default is not None and not isinstance(default, str):
                            raise ValueError("default must be raw CQL expression text")
                        new_text = upsert_parameter(text, name, ptype, default)
                    else:
                        raise ValueError(f"unknown action {action!r}")
                except ValueError as exc:
                    self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
                    return
                session = self.server.cell_registry.get(id(self.connection), lib_name)
                session.sync(new_text)
                from .resources import parse_parameters

                self._write_json(
                    200,
                    _envelope(
                        ok=True,
                        library=lib_name,
                        text=new_text,
                        parameters=[
                            {"name": p.name, "type": p.type, "default": p.default}
                            for p in parse_parameters(new_text)
                        ],
                    ),
                )
                return
            elif path == "/api/terminology/preview":
                self._route_terminology_preview(body)
                return
            elif path == "/api/terminology/search":
                self._route_terminology_search(body)
                return
            elif path == "/api/terminology/import":
                self._route_terminology_import(body)
                return
            elif path == "/api/terminology/config":
                self._route_terminology_config_post(body)
                return
            elif path == "/api/workspace/add-path":
                self._route_workspace_add_path(body)
                return
            elif path == "/api/tests/expected/save":
                self._route_tests_expected_post(body)
                return
            elif path == "/api/runs/clear":
                self._runlog().clear()
                self._write_json(200, _envelope(ok=True))
            elif path == "/api/tests/expected/delete":
                self._route_tests_expected_delete(body)
                return
            elif path == "/api/madie/import-package":
                self._route_madie_import_package(body)
                return
            elif path == "/api/madie/import-tests":
                self._route_madie_import_tests(body)
                return
            elif path == "/api/tests/capture":
                self._route_tests_capture(body)
                return
            elif path == "/api/tests/run":
                self._route_tests_run(body)
                return
            elif path == "/api/valueset/edit":
                # v3 Slice 1: valueset concept edit. Validate -> apply ->
                # validate_resource -> WRITE the workspace file (the valuesets/
                # dir is author-owned workspace, not a dependency dir) and set
                # the staleness flag (kernel restart reloads terminology).
                from .resources import ValueSetEdit, apply_valueset_edit, validate_valueset_edit

                vs_path = str(body.get("path") or "")
                snap = self.server.watcher.snapshot
                if vs_path not in [str(p) for p in snap.valuesets]:
                    self._write_json(
                        200,
                        _envelope(ok=False, diagnostics=[_diag(f"unknown valueset path {vs_path!r}")]),
                    )
                    return
                edit_raw = body.get("edit")
                if not isinstance(edit_raw, dict):
                    raise ValueError("edit must be an object")
                try:
                    edit = ValueSetEdit(
                        action=str(edit_raw.get("action") or ""),
                        system=edit_raw.get("system"),
                        code=edit_raw.get("code"),
                        display=edit_raw.get("display"),
                        old_code=edit_raw.get("old_code"),
                    )
                except TypeError as exc:
                    self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
                    return
                problems = validate_valueset_edit(edit)
                if problems:
                    self._write_json(200, _envelope(ok=False, diagnostics=[_diag(p) for p in problems]))
                    return
                try:
                    with open(vs_path, "r", encoding="utf-8") as fh:
                        resource = json.load(fh)
                except (OSError, json.JSONDecodeError) as exc:
                    self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
                    return
                new_resource = apply_valueset_edit(resource, edit)
                from fhir4ds.operations import validate_resource as ops_validate_resource

                vr = ops_validate_resource(new_resource)
                if not vr.valid:
                    self._write_json(
                        200,
                        _envelope(ok=False, diagnostics=[_diag(d) for d in vr.diagnostics]),
                    )
                    return
                with open(vs_path, "w", encoding="utf-8") as fh:
                    json.dump(new_resource, fh, indent=2)
                    fh.write("\n")
                self.server.valuesets_stale = True
                # Propagate staleness to every connected UI — the edit may
                # have originated from outside this page (API/another tab),
                # so the local onStaleChange path is not enough.
                self.server.watcher.bus.publish(
                    WorkspaceEvent(kind="stale", paths=[vs_path], valuesets_stale=True)
                )
                from fhir4ds.cql.loader.fhir_loader import _extract_codes_from_valueset_resource

                concepts = _extract_codes_from_valueset_resource(new_resource) or []
                from .resources import valueset_used_by

                lib_pairs = [(l.name, l.text or "") for l in snap.libraries]
                self._write_json(
                    200,
                    _envelope(
                        ok=True,
                        path=vs_path,
                        concepts=concepts,
                        used_by=valueset_used_by(new_resource, lib_pairs),
                        stale=True,
                    ),
                )
                return
            if path == "/api/translate":
                self._route_translate(body)
            elif path == "/api/evaluate":
                self._route_evaluate(body)
            elif path == "/api/verify":
                self._route_verify(body)
            elif path == "/api/explain":
                self._route_explain(body)
            elif path == "/api/measure/scaffold":
                self._route_measure_scaffold(body)
            elif path == "/api/measure/run":
                self._route_measure_run(body)
            elif path == "/api/measure/compare":
                self._route_measure_compare(body)
            elif path == "/api/measure/baseline/save":
                self._route_baseline_save(body)
            elif path == "/api/measure/baseline/delete":
                self._route_baseline_delete(body)
            elif path == "/api/view/run":
                self._route_view_run(body)
            elif path == "/api/resource/validate":
                self._route_resource_validate(body)
            elif path == "/api/resource/save":
                self._route_resource_save(body)
            elif path == "/api/kernel/restart":
                snap = self.server.watcher.snapshot
                kernel = self.server.kernel_manager.restart(snap)
                # Cell results evaluated against the OLD kernel are stale.
                self.server.cell_registry.mark_stale_all()
                # Restart reloads valuesets from disk — staleness clears.
                self.server.valuesets_stale = False
                # Let every connected UI clear its stale banner too.
                self.server.watcher.bus.publish(
                    WorkspaceEvent(kind="stale", paths=[], valuesets_stale=False)
                )
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
        # Shell-rebuild R2: bottom-bar ast tab — statement-level AST from
        # the parse capability (include_ast), attached when requested.
        if body.get("include_ast") and main is not None:
            try:
                from fhir4ds.operations import parse_cql as _parse_cql

                pr = _parse_cql(main.text, include_ast=True)
                if pr.ok and getattr(pr, "ast", None) is not None:
                    payload["ast"] = pr.ast
            except Exception:
                pass
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
        payload = kernel.verify(includes, main, cases, parameters=body.get("parameters"))
        self._write_json(200, payload)

    def _route_explain(self, body: dict[str, Any]) -> None:
        includes, main = self._resolve_main(body)
        patient = body.get("patient_id") or body.get("patient")
        if not isinstance(patient, str) or not patient:
            raise ValueError("patient_id is required")
        kernel = self.server.kernel_manager.current()
        payload = kernel.explain(includes, main, patient)
        self._write_json(200, payload)

    # -- measure scaffold/run (v3 slice 2) ----------------------------------

    def _route_measure_scaffold(self, body: dict[str, Any]) -> None:
        """Build a Measure PREVIEW from the library + explicit mapping.

        Never auto-saves: the caller receives the Measure resource and
        decides. ``mapping`` absent => bootstrap (define list only).
        """
        includes, main = self._resolve_main(body)
        mapping = body.get("mapping")
        if mapping is not None and not isinstance(mapping, list):
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[
                        _diag("mapping must be a list of {define, code} objects")
                    ],
                ),
            )
            return
        scoring = body.get("scoring") or "proportion"
        measure_name = body.get("measure_name") or "CleanroomMeasure"
        result = measure_from_definitions(
            includes,
            main,
            mapping=mapping,
            measure_name=measure_name,
            scoring=scoring,
        )
        self._write_json(200, result.to_dict())

    def _runlog(self):
        """RunLogStore for the workspace root (parity item 2)."""
        from .runlog import RunLogStore

        return RunLogStore(Path(self.server.watcher._cfg.root))

    def _dataset_ctx(self) -> tuple[list[str], int | None]:
        """Dataset names + patient count for run-history capture."""
        snap = self.server.watcher.snapshot
        names = [str(d) for d in (getattr(snap, "datasets", None) or [])]
        try:
            kernel = self.server.kernel_manager.current()
            rows = kernel.conn.execute(
                "SELECT id FROM resources WHERE resourceType = 'Patient'"
            ).fetchall()
            count = len({r[0] for r in rows if r[0] is not None})
        except Exception:
            count = None
        return names, count

    def _runlog_record(
        self,
        *,
        kind: str,
        target: str,
        status: str,
        duration_ms: int,
        row_count: int,
        summary=None,
        params=None,
        library_text: str | None = None,
        sql_text: str | None = None,
        error: str | None = None,
    ) -> None:
        """Record one run-history event (never raises into the request)."""
        try:
            if sql_text is not None:
                from .runlog import _sha

                store = getattr(self.server, "sql_store", None)
                if store is not None:
                    store[_sha(sql_text)] = sql_text
                    # bound the in-memory current-SQL store
                    if len(store) > 50:
                        for k in list(store.keys())[: len(store) - 50]:
                            del store[k]
            datasets, patient_count = self._dataset_ctx()
            self._runlog().record(
                kind=kind,
                target=target,
                status=status,
                duration_ms=duration_ms,
                row_count=row_count,
                summary=summary,
                params=params,
                library_text=library_text,
                sql_text=sql_text,
                error=error,
                datasets=datasets,
                patient_count=patient_count,
            )
        except Exception:
            pass

    def _expected_root(self) -> Path:
        """measures/expected dir (same resolution as baseline routes).

        S3b fix: resolve from the CONFIGURED measures dir — deriving from
        snapshot.measures (files) made the root drift once save populated
        measures/expected/patients/... (the saved files themselves became
        the "measures", moving the root under patients/<M>/expected).
        """
        cfg = getattr(self.server.watcher, "_cfg", None)
        measure_dirs = list(getattr(cfg, "measure_dirs", None) or [])
        if measure_dirs:
            return Path(measure_dirs[0]) / "expected"
        data_dirs = list(getattr(cfg, "data_dirs", None) or [])
        if data_dirs:
            return Path(data_dirs[0]).parent / "measures" / "expected"
        return Path("measures") / "expected"

    def _evaluate_measure_reports(self, body: dict[str, Any]):
        """Shared S3/S6 helper: run the measure.

        Returns (columns, counts, reports, None, sql) on success or
        (None, None, None, diagnostics, None) on failure.
        """
        measure = body.get("measure")
        if not isinstance(measure, dict):
            return None, None, None, [_diag("measure (JSON object) is required")], None
        try:
            cols = output_columns_from_measure(measure)
        except OperationError as exc:
            return None, None, None, [_diag(str(exc))], None
        includes, main = self._resolve_main(body)
        if main is None:
            return None, None, None, [_diag("could not resolve main library")], None
        kernel = self.server.kernel_manager.current()
        evd = evaluate_library(
            includes, main, None, kernel.conn,
            parameters=body.get("parameters"), output_columns=cols,
            emit_sql=True,
        ).to_dict()
        if not evd.get("ok"):
            return None, None, None, (evd.get("diagnostics") or [_diag("evaluation failed")]), None
        columns = list(cols.keys())
        mr = measure_report_from_rows(
            measure, evd.get("rows", []), columns,
            library_url=(measure.get("library") or [None])[0],
        )
        if not mr.ok:
            return None, None, None, (mr.to_dict().get("diagnostics") or [_diag("report build failed")]), None
        counts: dict[str, int] = {}
        for row in evd.get("rows", []):
            for col in columns:
                if row.get(col) is True:
                    counts[col] = counts.get(col, 0) + 1
        reports = [_regroup_report_populations(dict(r)) for r in mr.reports]
        return columns, counts, reports, None, evd.get("sql")

    def _route_tests_expected_get(self) -> None:
        """GET /api/tests/expected?measure=<name> — per-patient expected MRs."""
        from urllib.parse import parse_qs, urlparse

        from .expected_store import parse_expected_groups

        qs = parse_qs(urlparse(self.path).query)
        measure = (qs.get("measure") or [""])[0].strip()
        if not measure:
            self._write_json(200, _envelope(False, diagnostics=[_diag("measure query param is required")]))
            return
        try:
            reports = load_expected_reports(self._expected_root(), measure)
        except ValueError as exc:
            self._write_json(200, _envelope(False, diagnostics=[_diag(str(exc))]))
            return
        self._write_json(
            200,
            _envelope(
                measure=measure,
                patients=[
                    {
                        "patient": patient_from_report(r),
                        "report": r,
                        "groups": parse_expected_groups(r),
                    }
                    for r in reports
                ],
                count=len(reports),
            ),
        )

    def _route_tests_expected_post(self, body: dict[str, Any]) -> None:
        """POST /api/tests/expected — save per-patient expected reports.

        Body: {measure, reports: [MR, ...]} (MADiE cqfm-test-cases shape
        or our capture shape — groups parsed leniently on compare).
        """
        measure = (body.get("measure") or "").strip()
        reports = body.get("reports")
        if not measure or not isinstance(reports, list) or not reports:
            self._write_json(
                200,
                _envelope(False, diagnostics=[_diag("measure and non-empty reports[] are required")]),
            )
            return
        root = self._expected_root()
        written: list[str] = []
        try:
            for r in reports:
                if not isinstance(r, dict) or r.get("resourceType") != "MeasureReport":
                    raise ValueError("each report must be a MeasureReport object")
                if not is_test_case_report(r):
                    # Stamp our marker so MADiE tooling + our loader guard
                    # recognize the file (additive, per design §0.3).
                    r.setdefault("modifierExtension", []).append(
                        {"url": IS_TEST_CASES_URL_CONST, "valueBoolean": True}
                    )
                target = save_expected_report(root, measure, r)
                written.append(str(target))
        except (ValueError, OSError) as exc:
            self._write_json(200, _envelope(False, diagnostics=[_diag(str(exc))]))
            return
        self.server.watcher.bus.publish(WorkspaceEvent(kind="changed", paths=written))
        self._write_json(200, _envelope(measure=measure, written=written, count=len(written)))

    def _route_tests_expected_delete(self, body: dict[str, Any]) -> None:
        """POST /api/tests/expected/delete — remove one patient's expectation."""
        measure = (body.get("measure") or "").strip()
        patient = (body.get("patient") or "").strip()
        if not measure or not patient:
            self._write_json(
                200, _envelope(False, diagnostics=[_diag("measure and patient are required")])
            )
            return
        removed = delete_expected_report(self._expected_root(), measure, patient)
        self._write_json(200, _envelope(measure=measure, patient=patient, removed=removed))

    def _route_madie_import_package(self, body: dict[str, Any]) -> None:
        """POST /api/madie/import-package — import a MADiE package ZIP.

        Body: ``{zip_base64}`` (the exported measure package). Writes
        cql/, valuesets/, measures/ files and publishes a changed event.
        """
        import base64
        import binascii

        from .madie_import import import_package_zip

        raw = body.get("zip_base64")
        if not isinstance(raw, str) or not raw:
            self._write_json(
                200,
                _envelope(
                    False,
                    diagnostics=[_diag("zip_base64 is required (base64 of the MADiE package zip)")],
                ),
            )
            return
        try:
            zip_bytes = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            self._write_json(200, _envelope(False, diagnostics=[_diag(f"invalid base64: {exc}")]))
            return
        result = import_package_zip(self.server, zip_bytes)
        self._write_json(200, _envelope(**result))

    def _route_madie_import_tests(self, body: dict[str, Any]) -> None:
        """POST /api/madie/import-tests — import a MADiE test-case ZIP.

        Body: ``{zip_base64, measure_name?}``. Strips trailing
        isTestCases MeasureReports into the expected store; patient
        bundles land under ``data/<patientId>/``.
        """
        import base64
        import binascii

        from .madie_import import import_tests_zip

        raw = body.get("zip_base64")
        if not isinstance(raw, str) or not raw:
            self._write_json(
                200,
                _envelope(
                    False,
                    diagnostics=[_diag("zip_base64 is required (base64 of the MADiE test-case zip)")],
                ),
            )
            return
        try:
            zip_bytes = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            self._write_json(200, _envelope(False, diagnostics=[_diag(f"invalid base64: {exc}")]))
            return
        measure_name = body.get("measure_name")
        if measure_name is not None and not isinstance(measure_name, str):
            self._write_json(
                200, _envelope(False, diagnostics=[_diag("measure_name must be a string")])
            )
            return
        result = import_tests_zip(
            self.server, zip_bytes, measure_name=(measure_name or "").strip()
        )
        self._write_json(200, _envelope(**result))

    def _route_tests_capture(self, body: dict[str, Any]) -> None:
        """POST /api/tests/capture — run the measure, seed per-patient
        expected reports from ACTUAL results (editable grid start point)."""
        columns, counts, reports, diag, run_sql = self._evaluate_measure_reports(body)
        if diag is not None:
            self._write_json(200, _envelope(False, diagnostics=diag))
            return
        measure_name = (body.get("measure_name") or "").strip()
        if not measure_name:
            m = body.get("measure") or {}
            measure_name = (m.get("name") if isinstance(m, dict) else None) or "CleanroomMeasure"
        seed = []
        for r in reports:
            pid = patient_from_report(r)
            if pid is None:
                continue
            seed.append(
                build_expected_report(
                    pid,
                    parse_expected_groups(r),
                    library_url=r.get("measure"),
                )
            )
        self._write_json(
            200,
            _envelope(
                measure=measure_name,
                reports=seed,
                counts=counts,
                columns=columns,
                sql=run_sql,
            ),
        )

    def _route_tests_run(self, body: dict[str, Any]) -> None:
        """POST /api/tests/run — evaluate + diff per-patient vs expected.

        Body: {library, text?, measure, measure_name?, parameters?}.
        Returns per-patient rows {patient, code, expected, actual, pass}
        and a summary. Patients present only on one side surface as
        missing/extra rows.
        """
        import time as _time

        from .expected_store import parse_expected_groups

        _t0 = _time.monotonic()
        columns, counts, reports, diag, run_sql = self._evaluate_measure_reports(body)
        if diag is not None:
            m0 = body.get("measure") or {}
            self._runlog_record(
                kind="test",
                target=(m0.get("name") if isinstance(m0, dict) else None) or "Measure",
                status="error",
                duration_ms=int((_time.monotonic() - _t0) * 1000),
                row_count=0,
                params=body.get("parameters"),
                error=(diag or [{}])[0].get("message"),
            )
            self._write_json(200, _envelope(False, diagnostics=diag))
            return
        measure_name = (body.get("measure_name") or "").strip()
        if not measure_name:
            m = body.get("measure") or {}
            measure_name = (m.get("name") if isinstance(m, dict) else None) or "CleanroomMeasure"
        expected_reports = load_expected_reports(self._expected_root(), measure_name)

        expected_by_patient: dict[str, dict[str, int]] = {}
        for r in expected_reports:
            pid = patient_from_report(r)
            if pid is None:
                continue
            pop: dict[str, int] = {}
            for g in parse_expected_groups(r):
                for p in g.get("population", []):
                    pop[p["code"]] = pop.get(p["code"], 0) + p["count"]
            expected_by_patient[pid] = pop

        actual_by_patient: dict[str, dict[str, int]] = {}
        for r in reports:
            pid = patient_from_report(r)
            if pid is None:
                continue
            pop: dict[str, int] = {}
            for g in parse_expected_groups(r):
                for p in g.get("population", []):
                    pop[p["code"]] = pop.get(p["code"], 0) + p["count"]
            actual_by_patient[pid] = pop

        codes = sorted({c for p in expected_by_patient.values() for c in p} |
                       {c for p in actual_by_patient.values() for c in p})
        rows: list[dict[str, Any]] = []
        passed = failed = 0
        all_patients = sorted(set(expected_by_patient) | set(actual_by_patient))
        for pid in all_patients:
            exp = expected_by_patient.get(pid)
            act = actual_by_patient.get(pid)
            for code in codes:
                if exp is None:
                    rows.append({"patient": pid, "code": code, "expected": None,
                                 "actual": act.get(code, 0), "pass": False, "reason": "missing expectation"})
                    failed += 1
                    continue
                if act is None:
                    rows.append({"patient": pid, "code": code, "expected": exp.get(code, 0),
                                 "actual": None, "pass": False, "reason": "patient absent from run"})
                    failed += 1
                    continue
                e, a = exp.get(code, 0), act.get(code, 0)
                ok = e == a
                rows.append({"patient": pid, "code": code, "expected": e, "actual": a, "pass": ok})
                passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        self._runlog_record(
            kind="test",
            target=measure_name,
            status="pass" if failed == 0 else "fail",
            duration_ms=int((_time.monotonic() - _t0) * 1000),
            row_count=len(rows),
            summary={"passed": passed, "failed": failed},
            params=body.get("parameters"),
            sql_text=run_sql,
        )
        self._write_json(
            200,
            _envelope(
                measure=measure_name,
                rows=rows,
                total=passed + failed,
                passed=passed,
                failed=failed,
                ok=failed == 0,
                sql=run_sql,
            ),
        )

    def _route_measure_run(self, body: dict[str, Any]) -> None:
        """Run a Measure against the loaded dataset.

        Body: {library, text?, measure: {...}, parameters?}. Evaluates
        the mapped defines via output_columns narrowing (one evaluation)
        and returns population counts + per-patient MeasureReports.
        """
        measure = body.get("measure")
        if not isinstance(measure, dict):
            self._write_json(
                200,
                _envelope(ok=False, diagnostics=[_diag("measure (JSON object) is required")]),
            )
            return
        try:
            cols = output_columns_from_measure(measure)
        except OperationError as exc:
            self._write_json(
                200, _envelope(ok=False, diagnostics=[_diag(str(exc))])
            )
            return
        includes, main = self._resolve_main(body)
        kernel = self.server.kernel_manager.current()
        import time as _time

        _t0 = _time.monotonic()
        ev = evaluate_library(
            includes, main, None, kernel.conn,
            parameters=body.get("parameters"), output_columns=cols,
            emit_sql=True,
        )
        evd = ev.to_dict()
        measure_name = (
            measure.get("name") if isinstance(measure.get("name"), str) else "Measure"
        )
        if not evd.get("ok"):
            self._runlog_record(
                kind="measure",
                target=measure_name,
                status="error",
                duration_ms=int((_time.monotonic() - _t0) * 1000),
                row_count=0,
                params=body.get("parameters"),
                library_text=main.text if main is not None else None,
                error=(evd.get("diagnostics") or [{}])[0].get("message"),
            )
            self._write_json(200, evd)
            return
        columns = list(cols.keys())
        mr = measure_report_from_rows(
            measure, evd.get("rows", []), columns,
            library_url=(measure.get("library") or [None])[0],
        )
        if not mr.ok:
            self._write_json(200, mr.to_dict())
            return
        # Population counts over per-patient membership
        counts: dict[str, int] = {}
        for row in evd.get("rows", []):
            for col in columns:
                if row.get(col) is True:
                    counts[col] = counts.get(col, 0) + 1
        # Regroup per-patient populations into one MeasureReport group
        # entry per Measure.group (the operations layer intentionally
        # emits one group entry per population code — S-1 dual
        # representation — which the UI normalizes here so each report
        # mirrors the Measure's single-group shape).
        reports = [
            _regroup_report_populations(dict(r)) for r in mr.reports
        ]
        self._runlog_record(
            kind="measure",
            target=measure_name,
            status="pass",
            duration_ms=int((_time.monotonic() - _t0) * 1000),
            row_count=len(reports),
            summary={c: counts.get(c, 0) for c in columns},
            params=body.get("parameters"),
            library_text=main.text if main is not None else None,
            sql_text=evd.get("sql"),
        )
        self._write_json(
            200,
            {
                "schema": 1,
                "ok": True,
                "counts": {c: counts.get(c, 0) for c in columns},
                "columns": evd.get("column_types", {}),
                "rows": evd.get("rows", []),
                "reports": reports,
                # S6: surface the evaluation SQL (Show-SQL parity with
                # translate/evaluate; the UI previously discarded it).
                "sql": evd.get("sql"),
            },
        )

    def _route_measure_compare(self, body: dict[str, Any]) -> None:
        """POST /api/measure/compare — normalized diff of expected MeasureReports.

        Body: {library, text?, libraries?, measure: {...}, expected: [MR dict, ...],
        strict?: bool, parameters?}.
        Runs the measure over the loaded dataset (same path as /api/measure/run),
        aggregates expected and actual per population code (sum of count values
        across reports/groups), and returns rows [{code, expected, actual, delta}]
        where PASS = all deltas zero. Strict mode (default False) additionally
        requires the number of expected MeasureReports to equal the number of
        generated per-patient reports (loose mode compares counts only).
        """
        measure = body.get("measure")
        if not isinstance(measure, dict):
            self._write_json(
                200,
                _envelope(False, diagnostics=[_diag("measure must be a Measure resource object")]),
            )
            return
        expected = body.get("expected")
        if not isinstance(expected, list) or not all(isinstance(r, dict) for r in expected):
            self._write_json(
                200,
                _envelope(
                    False,
                    diagnostics=[_diag("expected must be a list of MeasureReport objects")],
                ),
            )
            return
        strict = bool(body.get("strict", False))

        includes, main = self._resolve_main(body)
        if main is None:
            return

        try:
            columns = output_columns_from_measure(measure)
        except OperationError as exc:
            self._write_json(
                200,
                _envelope(False, diagnostics=[_diag(str(exc))]),
            )
            return

        kernel = self.server.kernel_manager.current()
        evd = evaluate_library(
            includes,
            main,
            None,
            kernel.conn,
            parameters=body.get("parameters") or {},
            output_columns=columns,
        ).to_dict()
        if not evd.get("ok"):
            self._write_json(
                200,
                _envelope(
                    False,
                    diagnostics=(evd.get("diagnostics") or [_diag("evaluation failed")]),
                ),
            )
            return

        mr = measure_report_from_rows(
            measure,
            evd.get("rows", []),
            columns,
            library_url=(measure.get("library") or [None])[0],
        )
        actual_reports = [_regroup_report_populations(dict(r)) for r in mr.reports]

        def _pop_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
            counts: dict[str, int] = {}
            for rep in reports:
                for group in rep.get("group") or []:
                    for pop in group.get("population") or []:
                        code = None
                        for coding in (pop.get("code") or {}).get("coding") or []:
                            code = coding.get("code")
                            if code:
                                break
                        if not code:
                            continue
                        value = pop.get("count", 0)
                        counts[code] = counts.get(code, 0) + (value or 0)
            return counts

        exp_counts = _pop_counts(expected)
        act_counts = _pop_counts(actual_reports)
        codes: list[str] = []
        for code in list(exp_counts) + [c for c in act_counts if c not in exp_counts]:
            if code not in codes:
                codes.append(code)
        rows = [
            {
                "code": code,
                "expected": exp_counts.get(code, 0),
                "actual": act_counts.get(code, 0),
                "delta": act_counts.get(code, 0) - exp_counts.get(code, 0),
            }
            for code in codes
        ]
        pass_ = all(r["delta"] == 0 for r in rows)
        if strict:
            pass_ = pass_ and exp_counts == act_counts and len(expected) == len(actual_reports)

        self._write_json(
            200,
            {
                "schema": 1,
                "ok": True,
                "passed": pass_,
                "strict": strict,
                "rows": rows,
                "expected_measure": self._expected_measure_canonical(expected, measure),
            },
        )

    @staticmethod
    def _expected_measure_canonical(
        expected: list[dict[str, Any]], measure: dict[str, Any]
    ) -> dict[str, Any]:
        """On-load check: does expected[].measure canonical match the open Measure?

        Returns {matches: bool, canonical: str | None}. When any expected report
        carries a measure canonical and none matches the Measure's library url
        or url, matches=False (the UI surfaces a warning).
        """
        canonicals = set()
        for rep in expected:
            m = rep.get("measure")
            if isinstance(m, str) and m:
                canonicals.add(m)
        if not canonicals:
            return {"matches": True, "canonical": None}
        ref = (measure.get("url") or (measure.get("library") or [None])[0]) or ""
        return {"matches": ref in canonicals, "canonical": sorted(canonicals)[0]}

    def _route_baseline_save(self, body: dict[str, Any]) -> None:
        """v4.2: capture the CURRENT run output as an expected baseline.

        Body: {library, text?, libraries?, measure: {...}, parameters?,
        dataset?: str}. Reuses the scaffold+run path internally (the run
        evaluates against the dataset AS LOADED in the kernel — builder
        NDJSON appends only touch files, never the live kernel table), then
        writes measures/expected/<name>.baseline.vN.json (vN auto-increment,
        never overwrites) with a provenance wrapper. Publishes a 'changed'
        workspace event so other UIs refresh.
        """
        from datetime import datetime, timezone
        from pathlib import Path

        measure = body.get("measure")
        if not isinstance(measure, dict):
            self._write_json(
                200,
                _envelope(False, diagnostics=[_diag("measure must be a Measure resource object")]),
            )
            return
        name = (body.get("name") or "").strip()
        if not name or not isinstance(name, str):
            name = measure.get("name") or "CleanroomMeasure"
        if not all(ch.isalnum() or ch in "-_" for ch in name):
            self._write_json(
                200,
                _envelope(
                    False,
                    diagnostics=[_diag("baseline name must be alphanumeric/-/_")],
                ),
            )
            return

        includes, main = self._resolve_main(body)
        if main is None:
            return
        try:
            columns = output_columns_from_measure(measure)
        except OperationError as exc:
            self._write_json(200, _envelope(False, diagnostics=[_diag(str(exc))]))
            return

        kernel = self.server.kernel_manager.current()
        evd = evaluate_library(
            includes,
            main,
            None,
            kernel.conn,
            parameters=body.get("parameters") or {},
            output_columns=columns,
        ).to_dict()
        if not evd.get("ok"):
            self._write_json(
                200,
                _envelope(
                    False,
                    diagnostics=(evd.get("diagnostics") or [_diag("evaluation failed")]),
                ),
            )
            return
        mr = measure_report_from_rows(
            measure,
            evd.get("rows", []),
            columns,
            library_url=(measure.get("library") or [None])[0],
        )
        if not mr.ok:
            self._write_json(200, mr.to_dict())
            return
        reports = [_regroup_report_populations(dict(r)) for r in mr.reports]
        counts: dict[str, int] = {}
        for row in evd.get("rows", []):
            for col in columns:
                if row.get(col) is True:
                    counts[col] = counts.get(col, 0) + 1

        snap = self.server.watcher.snapshot
        dataset = body.get("dataset") or (
            str(snap.datasets[0]) if getattr(snap, "datasets", None) else None
        )
        prov = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "library": main.name,
            "dataset": dataset,
            "kernel_id": kernel.kernel_id,
            "patient_count": len(evd.get("rows", [])),
            "counts": {c: counts.get(c, 0) for c in columns},
        }

        # measures/expected under the workspace root: resolve from the FIRST
        # measure dir's parent when measure dirs exist, else the config data
        # dirs' parent — fall back to the server cwd.
        roots = [Path(str(d)).parent for d in (getattr(snap, "measures", None) or [])]
        if roots:
            expected_dir = roots[0] / "expected"
        else:
            cfg = getattr(self.server.watcher, "_cfg", None)
            data_dirs = list(getattr(cfg, "data_dirs", None) or [])
            expected_dir = (
                Path(data_dirs[0]).parent / "measures" / "expected"
                if data_dirs
                else Path("measures") / "expected"
            )
        expected_dir.mkdir(parents=True, exist_ok=True)
        n = 1
        target = expected_dir / f"{name}.baseline.v{n}.json"
        while target.exists():
            n += 1
            target = expected_dir / f"{name}.baseline.v{n}.json"
        wrapper = {
            "resourceType": "Bundle",
            "type": "collection",
            "provenance": prov,
            "reports": reports,
        }
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(wrapper, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        self.server.watcher.bus.publish(
            WorkspaceEvent(kind="changed", paths=[str(target)])
        )
        self._write_json(
            200,
            _envelope(
                path=str(target),
                name=target.name,
                provenance=prov,
                reports=len(reports),
            ),
        )

    def _route_baseline_delete(self, body: dict[str, Any]) -> None:
        """v4.2: delete a baseline file (guarded to an expected/ dir)."""
        from pathlib import Path

        p = body.get("path")
        if not isinstance(p, str) or not p:
            self._write_json(
                200, _envelope(False, diagnostics=[_diag("path is required")])
            )
            return
        target = Path(p).resolve()
        if target.parent.name != "expected":
            self._write_json(
                200,
                _envelope(
                    False,
                    diagnostics=[_diag("refusing to delete outside measures/expected/")],
                ),
            )
            return
        try:
            target.unlink()
        except OSError as exc:
            self._write_json(200, _envelope(False, diagnostics=[_diag(str(exc))]))
            return
        self.server.watcher.bus.publish(
            WorkspaceEvent(kind="changed", paths=[str(target)])
        )
        self._write_json(200, _envelope(deleted=str(target)))

    def _route_view_run(self, body: dict[str, Any]) -> None:
        """v3 Slice 4: run a ViewDefinition over the loaded dataset.

        Body: {text?: str (inline JSON — client buffer wins), path?: str}.
        Reads resources of the VD's `resource` type from the live kernel
        table, then flattens via operations flatten_view (isolated staging
        per SO-3 — the live resources table is never touched). Typed
        SOF-VD invariant diagnostics (ParseError/ValidationError messages)
        flow back inline for the pane to render.
        """
        text = body.get("text")
        v_path = body.get("path")
        if text is None and v_path is not None:
            snap = self.server.watcher.snapshot
            if str(v_path) not in [str(p) for p in snap.views]:
                self._write_json(
                    200,
                    _envelope(ok=False, diagnostics=[_diag(f"unknown view path {str(v_path)!r}")]),
                )
                return
            try:
                with open(str(v_path), "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError as exc:
                self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
                return
        if not isinstance(text, str) or not text.strip():
            self._write_json(
                200,
                _envelope(ok=False, diagnostics=[_diag("view text required (inline JSON or a known path)")]),
            )
            return
        try:
            vd = json.loads(text)
        except json.JSONDecodeError as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(f"invalid JSON: {exc}")]))
            return
        if not isinstance(vd, dict):
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag("view definition must be a JSON object")]))
            return
        resource_type = vd.get("resource")
        if not isinstance(resource_type, str) or not resource_type:
            self._write_json(
                200,
                _envelope(ok=False, diagnostics=[_diag("view definition requires a 'resource' binding")]),
            )
            return
        kernel = self.server.kernel_manager.current()
        explicit = body.get("resources")
        if explicit is not None:
            # v4.3: caller-supplied resources (e.g. the last measure run's
            # MeasureReports) are staged verbatim — the kernel table is not
            # consulted. Every entry must be a JSON object.
            if not isinstance(explicit, list) or not all(
                isinstance(r, dict) for r in explicit
            ):
                self._write_json(
                    200,
                    _envelope(
                        ok=False,
                        diagnostics=[_diag("resources must be a list of JSON objects")],
                    ),
                )
                return
            resources = explicit
        else:
            try:
                rows = kernel.conn.execute(
                    "SELECT resource FROM resources WHERE resourceType = ?",
                    [resource_type],
                ).fetchall()
            except Exception as exc:
                self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
                return
            resources = []
            for (raw,) in rows:
                try:
                    resources.append(json.loads(raw) if isinstance(raw, str) else raw)
                except json.JSONDecodeError:
                    continue
        import time as _time

        _t0 = _time.monotonic()
        result = flatten_view(vd, resources, kernel.conn)
        vd_name = vd.get("name") if isinstance(vd.get("name"), str) else (v_path or "inline view")
        self._runlog_record(
            kind="view",
            target=str(vd_name),
            status="pass" if result.ok else "fail",
            duration_ms=int((_time.monotonic() - _t0) * 1000),
            row_count=len(list(result.rows or [])),
            library_text=text,
            sql_text=result.sql,
            error=None if result.ok else (
                (result.diagnostics or [None] and [getattr(d, "message", str(d)) for d in result.diagnostics] or [None])[0]
            ),
        )
        self._write_json(
            200,
            {
                "schema": 1,
                "ok": bool(result.ok),
                "sql": result.sql,
                "columns": list(result.columns or []),
                "rows": list(result.rows or []),
                "diagnostics": [d.to_dict() if hasattr(d, "to_dict") else d for d in (result.diagnostics or [])],
                "resource_count": len(resources),
            },
        )

    def _route_resource_validate(self, body: dict[str, Any]) -> None:
        """v4.1 Resource Builder: validate a draft resource (save gate)."""
        from fhir4ds.operations.capabilities.validate import validate_resource

        resource = body.get("resource")
        if not isinstance(resource, dict):
            self._write_json(
                200,
                _envelope(ok=False, diagnostics=[_diag("resource must be a JSON object")]),
            )
            return
        result = validate_resource(resource)
        self._write_json(
            200,
            {
                "schema": 1,
                "ok": True,
                "valid": bool(result.valid),
                "resource_type": result.resource_type,
                "resource_id": result.resource_id,
                "diagnostics": [d.to_dict() if hasattr(d, "to_dict") else d for d in (result.diagnostics or [])],
            },
        )

    def _route_resource_save(self, body: dict[str, Any]) -> None:
        """v4.1 Resource Builder: validate then append one NDJSON line.

        The dataset path must live inside the workspace data dirs (author
        owned); the save publishes a data-hint event so the UI offers a
        kernel restart (data never auto-reloads).
        """
        from pathlib import Path as _Path

        from fhir4ds.operations.capabilities.validate import validate_resource

        resource = body.get("resource")
        if not isinstance(resource, dict):
            self._write_json(
                200,
                _envelope(ok=False, diagnostics=[_diag("resource must be a JSON object")]),
            )
            return
        raw_path = str(body.get("dataset_path") or "")
        if not raw_path:
            self._write_json(
                200,
                _envelope(ok=False, diagnostics=[_diag("dataset_path is required")]),
            )
            return
        snap = self.server.watcher.snapshot
        data_roots = [str(_Path(str(p)).parent.resolve()) for p in snap.datasets]
        default_root = next((r for r in data_roots if _Path(r).exists()), None)
        target = _Path(raw_path).resolve()
        allowed = any(str(target).startswith(root + os.sep) or str(target) == root for root in data_roots)
        if default_root is None:
            cfg_dirs = getattr(self.server.watcher.cfg, "data_dirs", None) or []
            cfg_roots = [str(_Path(str(p)).resolve()) for p in cfg_dirs]
            allowed = allowed or any(
                str(target).startswith(root + os.sep) or str(target) == root
                for root in cfg_roots
                if _Path(root).exists()
            )
            default_root = next((r for r in cfg_roots if _Path(r).exists()), None)
        if not allowed:
            self._write_json(
                200,
                _envelope(
                    ok=False,
                    diagnostics=[_diag(f"dataset path must be inside a workspace data dir: {raw_path!r}")],
                ),
            )
            return
        result = validate_resource(resource)
        if not result.valid:
            self._write_json(
                200,
                {
                    "schema": 1,
                    "ok": False,
                    "diagnostics": [
                        d.to_dict() if hasattr(d, "to_dict") else d
                        for d in (result.diagnostics or [])
                    ],
                },
            )
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(resource, ensure_ascii=False) + "\n")
        except OSError as exc:
            self._write_json(200, _envelope(ok=False, diagnostics=[_diag(str(exc))]))
            return
        self.server.watcher.bus.publish(WorkspaceEvent(kind="data-hint", paths=[str(target)]))
        self._write_json(200, _envelope(path=str(target), appended=True))

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
        sync_reply: list[dict[str, Any] | None] = [None]

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
                result = session.sync(str(msg.get("text") or ""))
                # ux3: include the boxes projection (spans + titles) so the
                # client can render card boxes over the single file.
                try:
                    from .cells import split_boxes

                    result["boxes"] = [
                        {
                            "title": b.title,
                            "title_source": b.title_source,
                            "kind": b.kind,
                            "name": b.name,
                            "start": b.start,
                            "end": b.end,
                        }
                        for b in split_boxes(str(msg.get("text") or ""))
                    ]
                except Exception:
                    pass
                sync_reply[0] = result

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
                    # A queued sync reply predates the run's inline
                    # session.sync (same buffer text); sending it after
                    # the result frame would clobber the run's OK states
                    # (client merges synced.states unconditionally).
                    sync_reply[0] = None
                    continue
                if sync_reply[0] is not None:
                    frame = json.dumps({"kind": "synced", **sync_reply[0]})
                    sync_reply[0] = None
                    self.wfile.write(ws_protocol.encode_text_frame(frame))
                    self.wfile.flush()
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
            self._ws_send({"kind": "runerror", "library": library, "cell": cell, "message": "library and cell are required"})
            return
        session = self.server.cell_registry.get(conn_id, library)
        if isinstance(text, str) and text:
            session.sync(text)

        run_seq = session.next_run_seq()
        try:
            names = session.plan(cell, mode)
        except KeyError:
            self._ws_send({"kind": "runerror", "library": library, "cell": cell, "message": f"unknown cell {cell!r}"})
            return
        except ValueError as exc:
            self._ws_send({"kind": "runerror", "library": library, "cell": cell, "message": str(exc)})
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
        import time as _time

        _t0 = _time.monotonic()
        envelope = kernel.evaluate(
            includes,
            main,
            output_columns={n: n for n in names},
        )
        self._runlog_record(
            kind="cell",
            target=f"{library}/{cell}",
            status="pass" if envelope.get("ok") else "error",
            duration_ms=int((_time.monotonic() - _t0) * 1000),
            row_count=len(envelope.get("rows", [])),
            params=None,
            library_text=composed,
            sql_text=envelope.get("sql"),
            error=None if envelope.get("ok") else _first_message(envelope),
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
                # Full envelope rows (patient_id + all cell columns) so the
                # UI can build patient-aware tables (Muse fix 1/5).
                "rows": rows,
                "timing_ms": envelope.get("timing_ms", {}),
                "per_cell": {
                    n: session.get_result(n).result for n in names if session.get_result(n)
                },
                "states": {n: OK for n in names},
                "stale_reasons": {},
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
