"""T7: the shipped WASM extension bundles are one known set.

``fhir4ds/wasm_extension_bundles.json`` records, for each side module, the
source copy, its sha256 and size, the DuckDB release it was built for and the
``@duckdb/duckdb-wasm`` version the apps pin. Every other copy in the tree must
be byte-identical to its source copy and every app must pin the same core, or
a browser loads a different engine than the one that was tested.

Observations are file-level gap kinds; the ledger decides whether an observed
gap is accepted (``contract.evaluate_files``). One observation cannot be
accepted: ``STALE_WASM_SOURCE`` (a C++ tree that changed after the bundle was
built from it) has exactly one remedy, a rebuild, so it is not a ledger kind.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .reference_bundle import REPO_ROOT

MANIFEST = REPO_ROOT / "fhir4ds" / "wasm_extension_bundles.json"
SCAN_ROOTS = ("web", "fhir4ds/devserver")
SKIP_DIRS = frozenset({"node_modules", ".temp", "dist", ".git", "build"})
_BUNDLE_FILE = re.compile(r"^(?P<extension>cql|fhirpath)\.duckdb_extension\.wasm$")


def load_manifest(path: Path | None = None) -> dict:
    return json.loads(Path(path or MANIFEST).read_text())


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


SOURCE_PATHS = {"cql": "extensions/cql/src", "fhirpath": "extensions/fhirpath/src"}
COMMON_PATH = "extensions/common"
_TREE_HASH = re.compile(r"^[0-9a-f]{40}$")


def head_trees(repo_root: Path, paths: list[str]) -> dict[str, str] | None:
    """Tree hashes of ``paths`` at ``HEAD``; ``""`` for a path HEAD does not have.

    ``None`` when git cannot answer (not a repository, git missing): a check
    that cannot look must not accuse.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-tree", "HEAD", *paths],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    found: dict[str, str] = {}
    for line in result.stdout.splitlines():
        meta, _, path = line.partition("\t")
        fields = meta.split()
        if path in paths and len(fields) == 3:
            found[path] = fields[2]
    return {path: found.get(path, "") for path in paths}


def stale_sources(manifest: dict, repo_root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """``extensions/<path> -> bundles`` built from a different tree than ``HEAD``.

    The manifest records the tree each bundle was built from. A C++ change
    that lands without a wasm rebuild leaves the browser on the older engine
    with nothing else to show for it: a new function name is caught by Tier B,
    a behaviour change is not.
    """
    wanted: dict[str, set[str]] = {}
    for bundle in manifest["bundles"]:
        source = bundle.get("source") or {}
        own = source.get(f"{bundle['extension']}_source")
        if isinstance(own, str) and _TREE_HASH.match(own):
            wanted.setdefault(SOURCE_PATHS[bundle["extension"]], set()).add(own)
        common = source.get("common_source")
        if isinstance(common, str) and _TREE_HASH.match(common):
            wanted.setdefault(COMMON_PATH, set()).add(common)
    if not wanted:
        return {}
    trees = head_trees(repo_root, sorted(wanted))
    if trees is None:
        return {}
    stale: dict[str, list[str]] = {}
    for bundle in manifest["bundles"]:
        source = bundle.get("source") or {}
        for path, key in ((SOURCE_PATHS[bundle["extension"]], f"{bundle['extension']}_source"), (COMMON_PATH, "common_source")):
            built_from = source.get(key)
            if isinstance(built_from, str) and _TREE_HASH.match(built_from) and trees.get(path) != built_from:
                stale.setdefault(path, []).append(bundle["extension"])
    return {path: sorted(set(extensions)) for path, extensions in stale.items()}


def observe(manifest: dict, repo_root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """File-level gap kinds observed right now: ``kind -> sorted targets``."""
    observed: dict[str, list[str]] = {"STALE_WASM_BUNDLE": [], "WASM_COPY_DRIFT": [], "PROVENANCE_UNKNOWN": [], "STALE_WASM_SOURCE": []}
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
    observed["STALE_WASM_SOURCE"] = [
        f"{path} ({', '.join(extensions)})" for path, extensions in stale_sources(manifest, repo_root).items()
    ]
    return {kind: sorted(targets) for kind, targets in observed.items() if targets}


def _tracked_bundles(repo_root: Path) -> list[Path]:
    """Every SHIPPED copy of a wasm bundle.

    Scoped to files git tracks: the gate is about what ships, and a developer's
    uncommitted build output is not shipped. A filesystem walk is the fallback
    for trees without git (an installed wheel), where everything present is
    shipped by definition.

    Concretely: ``web/website/build/`` is gitignored docusaurus output and
    contains copies of ``cql-macros.ts`` and the wasm bundles; walking it made
    every dev who had run a site build see ~18 phantom WASM_COPY_DRIFT entries.
    """
    tracked = _git_tracked_paths(repo_root)
    found: list[Path] = []
    if tracked is not None:
        for rel in tracked:
            if not rel.endswith(".duckdb_extension.wasm"):
                continue
            if not any(rel == root or rel.startswith(root + "/") for root in SCAN_ROOTS):
                continue
            path = repo_root / rel
            if path.exists():
                found.append(path)
        return sorted(found)
    for root in SCAN_ROOTS:
        base = repo_root / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.duckdb_extension.wasm")):
            if not SKIP_DIRS & set(path.relative_to(repo_root).parts):
                found.append(path)
    return found


def _git_tracked_paths(repo_root: Path) -> list[str] | None:
    """Paths git tracks under the repo root, or ``None`` when git is unusable."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    return [entry for entry in result.stdout.split("\0") if entry]
