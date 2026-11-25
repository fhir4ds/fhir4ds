"""Step 0 reference bundle: the browser macro statements, read as ground truth.

The cleanroom runtime registers ``CQL_MACRO_SQL`` from
``web/cql-cleanroom/src/lib/cql-macros.ts`` on its DuckDB-WASM connection
(``src/lib/duckdb-wasm.ts`` -> ``registerCQLMacros``). That file is THE reference
bundle for every browser-parity gate (FEATURE_WASM_PARITY_TEST_INFRA.md section
4.2). It is read by evaluating the module in node and printing the array. A
regex over the source is not acceptable: the scraper this replaces matched only
double-quoted strings and silently dropped 22 of the 116 statements (And/Or/Not/
Implies, IsNull family, Distinct, Coalesce, Left/Right, audit_*).

Node is an environment input. When it is absent the loader raises
``EnvironmentInputMissing``; tests skip naming that input, unless
``FHIR4DS_REQUIRE_WASM_PARITY=1`` turns it into a failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
REFERENCE_TS_MACRO_FILE = REPO_ROOT / "web" / "cql-cleanroom" / "src" / "lib" / "cql-macros.ts"
APP_TS_MACRO_GLOB = "web/*/src/lib/cql-macros.ts"
REQUIRE_ENV = "FHIR4DS_REQUIRE_WASM_PARITY"

# Appended to a throw-away copy of the module; the web source is never edited.
_PROBE_EXPORT = "\nexport { CQL_MACRO_SQL, MACRO_NAME_RE };\n"
_PROBE_SCRIPT = (
    "import(process.argv[1]).then(m => console.log(JSON.stringify({"
    "sql: m.CQL_MACRO_SQL,"
    "names: m.CQL_MACRO_SQL.map(s => s.match(m.MACRO_NAME_RE)?.[2]),"
    "registered: [...m.REGISTERED_MACRO_NAMES]})))"
)


class EnvironmentInputMissing(RuntimeError):
    """An input the gates need is not installed (node, chromium, a corpus)."""


def required(env_name: str = REQUIRE_ENV) -> bool:
    """True when a missing environment input must fail instead of skip."""
    return os.environ.get(env_name, "") == "1"


@dataclass(frozen=True)
class ReferenceBundle:
    """The reference statements exactly as the browser module registers them."""

    path: Path
    sha256: str
    statements: tuple[str, ...]
    names: tuple[str, ...]
    registered_names: tuple[str, ...]

    @property
    def lower_names(self) -> frozenset[str]:
        return frozenset(name.lower() for name in self.names)


def _first_error_line(stderr: str) -> str:
    """Node's error line, without its warning noise."""
    lines = [
        line
        for line in stderr.splitlines()
        if line.strip()
        and "ExperimentalWarning" not in line
        and not line.startswith(("(Use ", "(node:", "    at "))
    ]
    return lines[0][:400] if lines else "(no stderr)"


def _load_in_node(ts_file: Path) -> ReferenceBundle:
    raw = ts_file.read_bytes()
    with tempfile.TemporaryDirectory(prefix="wasm-parity-reference-") as tmp:
        # ``.mts`` is always ESM, so the copy needs no package.json.
        probe = Path(tmp) / "reference.mts"
        probe.write_bytes(raw + _PROBE_EXPORT.encode("utf-8"))
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                shutil.which("node"),
                "--experimental-strip-types",
                "-e",
                _PROBE_SCRIPT,
                str(probe),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"node could not evaluate {ts_file}: {_first_error_line(proc.stderr)}")
    payload_line = next(
        (ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("{")),
        None,
    )
    if payload_line is None:
        raise RuntimeError(
            f"node printed no bundle for {ts_file}: {_first_error_line(proc.stderr)}"
        )
    payload = json.loads(payload_line)
    statements = tuple(payload["sql"])
    names = tuple(payload["names"])
    if not statements or len(statements) != len(names):
        raise RuntimeError(f"{ts_file}: statements and names disagree")
    if any(not name for name in names) or len(set(names)) != len(names):
        raise RuntimeError(f"{ts_file}: macro names must be non-empty and unique")
    return ReferenceBundle(
        ts_file,
        hashlib.sha256(raw).hexdigest(),
        statements,
        names,
        tuple(payload["registered"]),
    )


def load_reference_bundle(path: Path | None = None) -> ReferenceBundle:
    """Evaluate the reference module in node and return its statements.

    Raises:
        EnvironmentInputMissing: node is not installed.
        RuntimeError: the module cannot be evaluated or is not a valid bundle.
    """
    ts_file = Path(path) if path is not None else REFERENCE_TS_MACRO_FILE
    if shutil.which("node") is None:
        raise EnvironmentInputMissing(
            "node is not installed; the reference macro bundle "
            f"({ts_file.relative_to(REPO_ROOT) if ts_file.is_relative_to(REPO_ROOT) else ts_file}) "
            "cannot be read. Set FHIR4DS_REQUIRE_WASM_PARITY=1 to make this a failure."
        )
    return _load_in_node(ts_file)


def app_macro_files(reference: Path = REFERENCE_TS_MACRO_FILE) -> list[tuple[Path, str]]:
    """Every ``web/*/src/lib/cql-macros.ts`` with its status.

    Status is ``reference`` for the reference itself, ``identical`` for a
    byte-identical copy, ``differs`` otherwise. The fhir4px copy is
    cross-repo and cannot be seen here.
    """
    reference_bytes = Path(reference).read_bytes()
    out: list[tuple[Path, str]] = []
    for path in sorted(REPO_ROOT.glob(APP_TS_MACRO_GLOB)):
        if path == Path(reference):
            status = "reference"
        elif path.read_bytes() == reference_bytes:
            status = "identical"
        else:
            status = "differs"
        out.append((path, status))
    return out
