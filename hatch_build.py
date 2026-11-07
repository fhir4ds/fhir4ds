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
        # DuckDB 1.5.x build line only (never grab a v2.* build).
        "version_prefix": "v1.",
    },
    {
        "name": "cql",
        "filename": "cql.duckdb_extension",
        "env_var": "DUCKDB_CQL_EXT",
        "cpp_dir": "extensions/cql",
        "dst_dir": "fhir4ds/cql/duckdb/extensions",
        "version_prefix": "v1.",
    },
    {
        # DuckDB 2.0.x build line (second bundle; OPTIONAL until the 2.0
        # build lands — a wheel without it still builds and works on 1.x;
        # the runtime selection warns on 2.x without it, per the design).
        "name": "fhirpath",
        "filename": "fhirpath.duckdb2_extension",
        "env_var": "DUCKDB_FHIRPATH_EXT2",
        "cpp_dir": "extensions/fhirpath",
        "dst_dir": "fhir4ds/fhirpath/duckdb/extensions",
        "version_prefix": "v2.",
    },
    {
        "name": "cql",
        "filename": "cql.duckdb2_extension",
        "env_var": "DUCKDB_CQL_EXT2",
        "cpp_dir": "extensions/cql",
        "dst_dir": "fhir4ds/cql/duckdb/extensions",
        "version_prefix": "v2.",
    },
]


def _discover_versions(repo_dir: Path, prefix: str | None = None) -> list[str]:
    """Auto-discover DuckDB versions from the build/release/repository/ tree.

    Scans the directory for ``v*`` subdirectories and returns them sorted
    newest-first so the most recent build is found first.  Falls back to an
    empty list when the directory doesn't exist (e.g. clean CI checkout).
    """
    if not repo_dir.is_dir():
        return []
    versions = sorted(
        (
            d.name
            for d in repo_dir.iterdir()
            if d.is_dir()
            and d.name.startswith("v")
            and (prefix is None or d.name.startswith(prefix))
        ),
        reverse=True,
    )
    return versions


def _pinned_duckdb_floor() -> str | None:
    """The duckdb version floor from the MAIN dependency pin (``duckdb>=X.Y.Z,<2``).

    The default-named extension slots (``*.duckdb_extension``) must be built
    for the duckdb version a clean ``pip install`` actually resolves first —
    the pin's floor. The runtime dispatches newer/2.0 duckdb installs onto the
    ``*.duckdb156_extension`` / ``*.duckdb2_extension`` variant bundles.

    Returns ``None`` when the pin cannot be parsed (guard disabled; the
    hook then falls back to newest-v1-wins with a warning).
    """
    import re

    try:
        text = Path("pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return None
    # First duckdb requirement with a >= floor, outside the [duckdb2] extra
    # comment block: match ``"duckdb>=X.Y.Z"`` (the main + serve extras both
    # restate it; the first occurrence is the main dependency).
    m = re.search(r'"duckdb>=((\d+)\.(\d+)(?:\.(\d+))?)', text)
    return m.group(1) if m else None


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
        versions = _discover_versions(repo_dir, ext_cfg.get("version_prefix"))

        # ABI guard (v0.0.22): the DEFAULT slots (v1-prefixed entries) must
        # ship a binary built for the pyproject duckdb pin's FLOOR — a newer
        # build in the tree (e.g. v1.5.6 while the pin floors at 1.5.5)
        # silently ships an unloadable default binary on clean installs.
        # Exact env-var overrides (path 1) bypass the guard intentionally.
        guard_note = ""
        if ext_cfg.get("version_prefix") == "v1." and versions and not os.environ.get(ext_cfg["env_var"]):
            floor = _pinned_duckdb_floor()
            if floor is not None:
                wanted = f"v{floor}"
                if wanted in versions:
                    if versions[0] != wanted:
                        guard_note = (
                            f"[fhir4ds] ABI guard: default slot pinned to {wanted} "
                            f"(pyproject duckdb>={floor}); ignoring newer build "
                            f"{versions[0]} — build it for the *156/*2 variant slots instead."
                        )
                    versions = [wanted]
                else:
                    if dst.exists():
                        # The committed default slot (git-provenance build)
                        # IS the source of truth when the build tree lacks a
                        # floor-matching build — keep it, never clobber with
                        # a wrong-ABI newer build.
                        self.app.display_warning(
                            f"[fhir4ds] ABI guard: pyproject pins duckdb>={floor} but "
                            f"no {wanted} build of {ext_cfg['name']} exists under "
                            f"{repo_dir} (found: {', '.join(versions)}). Keeping the "
                            f"committed {dst.name} (set {ext_cfg['env_var']} to "
                            f"override)."
                        )
                        return
                    raise RuntimeError(
                        f"[fhir4ds] ABI guard: pyproject pins duckdb>={floor} but no "
                        f"{wanted} build of {ext_cfg['name']} exists under {repo_dir} "
                        f"(found: {', '.join(versions)}), and no committed default "
                        f"binary is present. Build the extension against duckdb "
                        f"{floor} submodules, or set {ext_cfg['env_var']} to "
                        f"bundle a specific binary."
                    )

        for platform in PLATFORMS:
            for ver in versions:
                candidates.append(repo_dir / ver / platform / ext_cfg["filename"])
        if guard_note:
            self.app.display_warning(guard_note)

        # 3. Legacy sibling directory layout (fallback)
        legacy_repo = Path(f"duckdb-{ext_cfg['name']}-cpp") / "build" / "release" / "repository"
        legacy_versions = _discover_versions(legacy_repo, ext_cfg.get("version_prefix"))
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
