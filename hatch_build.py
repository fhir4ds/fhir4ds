"""
Hatchling build hook: optionally bundle compiled C++ DuckDB extensions.

Searches for pre-compiled FHIRPath and CQL extension binaries and copies them
into the wheel under their respective package directories:

- fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension
- fhir4ds/cql/duckdb/extensions/cql.duckdb_extension

At runtime, registration functions check for these bundled files before
falling back to the Python UDF implementation.

In CI, set DUCKDB_FHIRPATH_EXT / DUCKDB_CQL_EXT to override search paths:
    DUCKDB_FHIRPATH_EXT=/build/fhirpath.duckdb_extension pip wheel .
    DUCKDB_CQL_EXT=/build/cql.duckdb_extension pip wheel .
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


PLATFORMS = [
    "linux_amd64",
    "linux_amd64_gcc4",
    "osx_amd64",
    "osx_arm64",
    "windows_amd64",
]

EXTENSIONS = [
    {
        "name": "fhirpath",
        "filename": "fhirpath.duckdb_extension",
        "env_var": "DUCKDB_FHIRPATH_EXT",
        "cpp_dir": "extensions/fhirpath",
        "dst_dir": "fhir4ds/fhirpath/duckdb/extensions",
    },
    {
        "name": "cql",
        "filename": "cql.duckdb_extension",
        "env_var": "DUCKDB_CQL_EXT",
        "cpp_dir": "extensions/cql",
        "dst_dir": "fhir4ds/cql/duckdb/extensions",
    },
]


def _discover_versions(repo_dir: Path) -> list[str]:
    """Auto-discover DuckDB versions from the build/release/repository/ tree.

    Scans the directory for ``v*`` subdirectories and returns them sorted
    newest-first so the most recent build is found first.  Falls back to an
    empty list when the directory doesn't exist (e.g. clean CI checkout).
    """
    if not repo_dir.is_dir():
        return []
    versions = sorted(
        (d.name for d in repo_dir.iterdir() if d.is_dir() and d.name.startswith("v")),
        reverse=True,
    )
    return versions


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        for ext_cfg in EXTENSIONS:
            self._bundle_extension(ext_cfg, build_data)

    def _bundle_extension(self, ext_cfg: dict, build_data: dict) -> None:
        dst_dir = Path(ext_cfg["dst_dir"])
        dst = dst_dir / ext_cfg["filename"]

        candidates: list[Path] = []

        # 1. Environment variable override
        if env_path := os.environ.get(ext_cfg["env_var"]):
            candidates.append(Path(env_path))

        # 2. Relocated extensions/ directory (new layout)
        #    Auto-discover DuckDB versions so the list never goes stale.
        repo_dir = Path(ext_cfg["cpp_dir"]) / "build" / "release" / "repository"
        versions = _discover_versions(repo_dir)
        for platform in PLATFORMS:
            for ver in versions:
                candidates.append(repo_dir / ver / platform / ext_cfg["filename"])

        # 3. Legacy sibling directory layout (fallback)
        legacy_repo = Path(f"duckdb-{ext_cfg['name']}-cpp") / "build" / "release" / "repository"
        legacy_versions = _discover_versions(legacy_repo)
        for platform in PLATFORMS:
            for ver in legacy_versions:
                candidates.append(legacy_repo / ver / platform / ext_cfg["filename"])

        for src in candidates:
            if src.exists() and src.is_file():
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                build_data.setdefault("artifacts", []).append(str(dst))
                self.app.display_info(
                    f"[fhir4ds] Bundled C++ {ext_cfg['name']} extension: {src} → {dst}"
                )
                return

        self.app.display_info(
            f"[fhir4ds] No compiled C++ {ext_cfg['name']} extension found — "
            f"Python UDF fallback will be used at runtime. "
            f"Set {ext_cfg['env_var']} to bundle the binary."
        )
