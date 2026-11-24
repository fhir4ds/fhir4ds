"""T7: the shipped WASM extension bundles are one known set.

``fhir4ds/wasm_extension_bundles.json`` records, for each side module, the
source copy, its sha256 and size, the DuckDB release it was built for and the
``@duckdb/duckdb-wasm`` version the apps pin. Every other copy in the tree must
be byte-identical to its source copy and every app must pin the same core, or
a browser loads a different engine than the one that was tested.

Observations are file-level gap kinds; the ledger decides whether an observed
gap is accepted (``contract.evaluate_files``).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .reference_bundle import REPO_ROOT

MANIFEST = REPO_ROOT / "fhir4ds" / "wasm_extension_bundles.json"
SCAN_ROOTS = ("web", "fhir4ds/devserver")
SKIP_DIRS = frozenset({"node_modules", ".temp", "dist", ".git"})
_BUNDLE_FILE = re.compile(r"^(?P<extension>cql|fhirpath)\.duckdb_extension\.wasm$")


def load_manifest(path: Path | None = None) -> dict:
    return json.loads(Path(path or MANIFEST).read_text())


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def observe(manifest: dict, repo_root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """File-level gap kinds observed right now: ``kind -> sorted targets``."""
    observed: dict[str, list[str]] = {"STALE_WASM_BUNDLE": [], "WASM_COPY_DRIFT": [], "PROVENANCE_UNKNOWN": []}
    expected: dict[str, str] = {}
    for bundle in manifest["bundles"]:
        source = repo_root / bundle["path"]
        expected[bundle["extension"]] = bundle["sha256"].lower()
        if not source.exists() or sha256_of(source) != bundle["sha256"].lower() or source.stat().st_size != bundle["size"]:
            observed["STALE_WASM_BUNDLE"].append(bundle["path"])
    for path in _tracked_bundles(repo_root):
        match = _BUNDLE_FILE.match(path.name)
        if match and sha256_of(path) != expected.get(match.group("extension")):
            observed["WASM_COPY_DRIFT"].append(path.relative_to(repo_root).as_posix())
    for package in sorted((repo_root / "web").glob("*/package.json")):
        pinned = json.loads(package.read_text()).get("dependencies", {}).get("@duckdb/duckdb-wasm")
        if pinned is not None and pinned != manifest["duckdb_wasm_version"]:
            observed["WASM_COPY_DRIFT"].append(package.relative_to(repo_root).as_posix())
    observed["PROVENANCE_UNKNOWN"] = [b["path"] for b in manifest["bundles"] if not b.get("source")]
    return {kind: sorted(targets) for kind, targets in observed.items() if targets}


def _tracked_bundles(repo_root: Path) -> list[Path]:
    found: list[Path] = []
    for root in SCAN_ROOTS:
        base = repo_root / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.duckdb_extension.wasm")):
            if not SKIP_DIRS & set(path.relative_to(repo_root).parts):
                found.append(path)
    return found
