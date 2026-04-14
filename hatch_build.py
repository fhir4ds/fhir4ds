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
VERSIONS = ["v1.5.1", "v1.5.0", "v1.4.0"]

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
        for platform in PLATFORMS:
            for ver in VERSIONS:
                candidates.append(
                    Path(ext_cfg["cpp_dir"])
                    / "build"
                    / "release"
                    / "repository"
                    / ver
                    / platform
                    / ext_cfg["filename"]
                )

        # 3. Legacy sibling directory layout (fallback)
        legacy_dir = f"duckdb-{ext_cfg['name']}-cpp"
        for platform in PLATFORMS:
            for ver in VERSIONS:
                candidates.append(
                    Path(legacy_dir)
                    / "build"
                    / "release"
                    / "repository"
                    / ver
                    / platform
                    / ext_cfg["filename"]
                )

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
