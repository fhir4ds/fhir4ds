"""Tier B: the real browser engine (duckdb-wasm + the SHIPPED wasm extension bundles).

The simulated browser surface (Tier A) proves the *contract* on desktop DuckDB; it cannot see
the engine (binder, planner, Arrow transport) and it runs the x86 bundles, not the wasm ones.
This module boots the real thing: a static ``harness.html`` that opens duckdb-wasm exactly like
``web/cql-cleanroom/src/lib/duckdb-wasm.ts`` (same npm package, same worker, same open flags),
served on an ephemeral localhost port with COOP/COEP, driven headless by the cleanroom's
Playwright package. Each :meth:`RealWasmEngine.job` is one browser boot (~0.5 s), zero retries.

Values cross the boundary as VARCHAR plus ``typeof()``. That is the faithful transport: the
apps' ``castBigIntToDouble`` open flag turns BIGINT/DECIMAL Arrow values into JS doubles, so the
raw Arrow path is a separate, explicitly measured subject (``raw()`` / gate B4).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .reference_bundle import REPO_ROOT, EnvironmentInputMissing
from .shipped_bundles import load_manifest

NODE_MODULES = REPO_ROOT / "web" / "cql-cleanroom" / "node_modules"
_ASSETS = Path(__file__).with_name("real")
RUNNER = _ASSETS / "run.mjs"
HARNESS = _ASSETS / "harness.html"
# URL path -> directory inside node_modules (the harness import map and the duckdb package
# resolve these as bare specifiers).
_LINKS = {
    "duckdb": "@duckdb/duckdb-wasm/dist",
    "arrow": "apache-arrow",
    "tslib": "tslib",
    "flatbuffers": "flatbuffers",
}
# duckdb-wasm resolves a side module relative to the MAIN duckdb-eh.wasm directory, not to the
# registered URL, so the extension bundles must sit beside it.
_RUNTIME_FILES = ("duckdb-eh.wasm", "duckdb-browser-eh.worker.js")
DEFAULT_HARD_TIMEOUT_MS = 120_000


class RealEngineError(RuntimeError):
    """The real engine failed for a reason that is a finding, not a missing input."""


def _node_modules() -> Path:
    """The web apps' installed packages: the repo's own, or ``FHIR4DS_WASM_NODE_MODULES``.

    Lane worktrees do not carry ``node_modules``; point the variable at any checkout that ran
    ``npm install`` in ``web/cql-cleanroom`` to run the real-browser gates there.
    """
    import resource

    soft, _hard = resource.getrlimit(resource.RLIMIT_AS)
    if soft != resource.RLIM_INFINITY:
        # chromium cannot start with a capped address space (the V8 sandbox reservation
        # fails with SIGTRAP); this gate is light, so it is the one command that runs
        # WITHOUT scripts/capped.sh.
        raise EnvironmentInputMissing(
            f"RLIMIT_AS is capped at {soft} bytes (scripts/capped.sh / ulimit -v): headless "
            "chromium cannot start; run the Tier B gates without the cap"
        )
    override = os.environ.get("FHIR4DS_WASM_NODE_MODULES")
    base = Path(override).resolve() / "web" / "cql-cleanroom" / "node_modules" if override else NODE_MODULES
    needed = (
        base / "@duckdb" / "duckdb-wasm" / "dist" / "duckdb-eh.wasm",
        base / "playwright" / "index.js",
    )
    missing = [str(path.relative_to(base)) for path in needed if not path.exists()]
    missing += [target for target in _LINKS.values() if not (base / target).exists()]
    if missing:
        raise EnvironmentInputMissing(
            f"{base} is incomplete ({', '.join(missing)}): run `npm install` in "
            "web/cql-cleanroom, or set FHIR4DS_WASM_NODE_MODULES to a checkout root that has it"
        )
    return base


def _stage(root: Path, node_modules: Path) -> None:
    root.mkdir(parents=True)
    shutil.copy(HARNESS, root / "harness.html")
    for link, target in _LINKS.items():
        (root / link).symlink_to(node_modules / target, target_is_directory=True)
    runtime = root / "runtime"
    runtime.mkdir()
    dist = node_modules / _LINKS["duckdb"]
    for name in _RUNTIME_FILES:
        (runtime / name).symlink_to(dist / name)
    for bundle in load_manifest()["bundles"]:
        source = REPO_ROOT / bundle["path"]
        if not source.exists():
            raise EnvironmentInputMissing(f"shipped wasm bundle missing: {bundle.path}")
        (runtime / source.name).symlink_to(source)


class _Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".mjs": "text/javascript",
        ".js": "text/javascript",
    }

    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args: Any) -> None:  # noqa: D102 - keep the gate output clean
        return


@contextmanager
def real_engine(hard_timeout_ms: int = DEFAULT_HARD_TIMEOUT_MS):
    """Serve the harness and yield one :class:`RealWasmEngine`; tears both down afterwards."""
    node_modules = _node_modules()
    with tempfile.TemporaryDirectory(prefix="fhir4ds-wasm-parity-") as tmp:
        root = Path(tmp) / "www"
        _stage(root, node_modules)
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(_Handler, directory=str(root))  # type: ignore[arg-type]
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/harness.html"
        try:
            yield RealWasmEngine(url, node_modules, Path(tmp), hard_timeout_ms)
        finally:
            server.shutdown()
            server.server_close()


def plain(value: Any) -> Any:
    """``[tag, payload]`` from the harness -> the plain Python value."""
    if value is None:
        return None
    tag, payload = value
    return {"bigint": int, "number": float, "string": str, "boolean": bool}.get(tag, lambda x: x)(
        payload
    )


class RealWasmEngine:
    """Headless duckdb-wasm with the shipped wasm bundles loaded."""

    def __init__(
        self,
        url: str,
        node_modules: Path,
        workdir: Path,
        hard_timeout_ms: int = DEFAULT_HARD_TIMEOUT_MS,
    ) -> None:
        self.url = url
        self._node_modules = node_modules
        self._workdir = workdir
        self._hard_timeout_ms = hard_timeout_ms
        self._boot = 0
        self._meta: dict[str, Any] = {}
        self._macros: list[str] = []

    # -- plumbing ---------------------------------------------------------------------
    def job(
        self,
        *,
        statements: Any = (),
        macros: list[str] | None = None,
        hard_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """Boot one browser, run the job, return the runner's output object."""
        self._boot += 1
        limit_ms = hard_timeout_ms or self._hard_timeout_ms
        job_path = self._workdir / f"job{self._boot}.json"
        out_path = self._workdir / f"job{self._boot}.out.json"
        job_path.write_text(
            json.dumps(
                {
                    "macros": self._macros if macros is None else macros,
                    "statements": list(statements),
                    "hardTimeoutMs": limit_ms,
                }
            )
        )
        command = [
            "node",
            str(RUNNER),
            str(self._node_modules),
            self.url,
            str(job_path),
            str(out_path),
        ]
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                command, capture_output=True, text=True, timeout=limit_ms / 1000 + 60
            )
        except FileNotFoundError as exc:
            raise EnvironmentInputMissing("node is required for the real-browser gates") from exc
        except subprocess.TimeoutExpired as exc:
            raise RealEngineError(f"real engine did not return within {limit_ms} ms") from exc
        out: dict[str, Any] = json.loads(out_path.read_text()) if out_path.exists() else {}
        if out.get("environment") == "chromium":
            raise EnvironmentInputMissing(
                "headless chromium could not start: run `npx playwright install chromium` in "
                f"web/cql-cleanroom ({str(out.get('error'))[:300]})"
            )
        booted = (out.get("status") or {}).get("booted")
        if proc.returncode != 0 or out.get("error") or not booted:
            detail = out.get("error") or (out.get("status") or {}).get("error") or proc.stderr[-400:]
            raise RealEngineError(f"real engine boot failed (exit {proc.returncode}): {detail}")
        failed = (out.get("macros") or {}).get("failed") or []
        if failed:
            raise RealEngineError(
                f"{len(failed)} macro statements failed to register in the browser: {failed[:3]}"
            )
        if not self._meta:
            self._meta = out
        return out

    def run(self, statements: Any) -> list[dict[str, Any]]:
        """Run ``[(label, sql), ...]`` in one boot; one result object per statement."""
        out = self.job(statements=statements)
        results = out.get("results") or []
        if len(results) != len(statements):
            raise RealEngineError(
                f"real engine returned {len(results)} results for {len(statements)} statements"
            )
        return results

    # -- facts about the engine -------------------------------------------------------
    @property
    def node_modules(self) -> Path:
        return self._node_modules

    @property
    def version(self) -> str:
        if not self._meta:
            self.job()
        return str(self._meta["version"])

    @property
    def load_report(self) -> dict[str, Any]:
        if not self._meta:
            self.job()
        return dict(self._meta["loads"])

    def use_reference(self, reference: Any) -> None:
        """Register these TS macro statements in EVERY boot.

        Each :meth:`job` is a fresh browser and a fresh in-memory database, so nothing
        registered in one job survives into the next.
        """
        self._macros = list(reference.statements)

    def names(self) -> frozenset[str]:
        """Every catalog name (functions and macros), lower-cased."""
        rows = self.run(
            [("catalog", "SELECT DISTINCT lower(function_name) AS name FROM duckdb_functions()")]
        )[0]["rows"]
        return frozenset(row["name"][1] for row in rows)

    def macro_definitions(self) -> dict[str, str]:
        rows = self.run(
            [
                (
                    "macros",
                    "SELECT lower(function_name) AS name, macro_definition AS body "
                    "FROM duckdb_functions() WHERE function_type = 'macro'",
                )
            ]
        )[0]["rows"]
        return {
            row["name"][1]: " ".join(str(row["body"][1]).split()) for row in rows if row["body"]
        }

    # -- evaluation -------------------------------------------------------------------
    def typed(self, expressions: Any) -> list[tuple[str | None, str | None, str | None]]:
        """``(value_text, type, error)`` per expression: VARCHAR + typeof(), the faithful path."""
        statements = [
            (
                str(i),
                f"SELECT ({expr})::VARCHAR AS value, typeof(({expr})) AS type",
            )
            for i, expr in enumerate(expressions)
        ]
        out = []
        for result in self.run(statements):
            if not result["ok"]:
                out.append((None, None, result["error"]))
            else:
                row = result["rows"][0]
                out.append((plain(row["value"]), plain(row["type"]), None))
        return out

    def raw(self, expressions: Any) -> list[tuple[str | None, str | None, str | None]]:
        """``(arrow_value_json, type, error)`` per expression: the apps' Arrow transport.

        No cast: the value is whatever duckdb-wasm's Arrow reader hands JavaScript under the
        apps' ``castBigIntToDouble`` flag (the harness tags each JS value).
        """
        statements = [
            (str(i), f"SELECT ({expr}) AS v, typeof(({expr})) AS type")
            for i, expr in enumerate(expressions)
        ]
        out = []
        for result in self.run(statements):
            if not result["ok"]:
                out.append((None, None, result["error"]))
            else:
                row = result["rows"][0]
                out.append((json.dumps(row["v"], sort_keys=True), plain(row["type"]), None))
        return out


class RealConnection:
    """DBAPI-shaped adapter: a suite evaluator's statements run on the real engine in batches.

    ``execute`` runs one statement per boot (setup DDL). ``execute_many`` is the batched path
    ``evaluators.cql`` detects: it evaluates translated expressions in chunks of one browser
    boot each and returns ``run_cql.TestExecution`` objects built from the VARCHAR transport.
    """

    def __init__(self, engine: RealWasmEngine, chunk_size: int = 250) -> None:
        self._engine = engine
        self._chunk_size = chunk_size

    def execute(self, sql: str) -> RealConnection:
        result = self._engine.run([("statement", sql)])[0]
        if not result["ok"]:
            raise RealEngineError(str(result["error"]))
        return self

    def fetchone(self) -> None:
        return None

    def execute_many(self, sqls: Any) -> list[Any]:
        import sys

        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from conformance.scripts import run_cql

        out: list[Any] = []
        sql_list = list(sqls)
        for start in range(0, len(sql_list), self._chunk_size):
            chunk = sql_list[start : start + self._chunk_size]
            for text, type_name, error in self._engine.typed(chunk):
                if error is not None:
                    out.append(run_cql.TestExecution(None, None, error))
                else:
                    out.append(run_cql.rebuild_test_value(text, type_name))
        return out
