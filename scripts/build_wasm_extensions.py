#!/usr/bin/env python3
"""Build, install and verify the WASM extension bundles the web apps ship.

duckdb-wasm's core is built from one DuckDB release. The CQL and FHIRPath side
modules must be built for that same release (``duckdb_abi`` in
``fhir4ds/wasm_extension_bundles.json``) or ``LOAD`` fails in the browser. The
manifest is the single source of truth: the source copy, sha256 and size of each
bundle, where it is installed, and the build's provenance.

    python3 scripts/build_wasm_extensions.py --verify            # default; CI and release gate
    python3 scripts/build_wasm_extensions.py --build             # rebuild every bundle
    python3 scripts/build_wasm_extensions.py --build --extension cql --dry-run

``--verify`` fails when a shipped copy differs from its manifest source copy,
an app pins another ``@duckdb/duckdb-wasm``, or the manifest no longer matches
the file on disk. A bundle without recorded provenance is a warning unless
``--require-source`` is given.

``--build`` pins each extension's ``duckdb`` submodule to the ABI tag, builds
with the emscripten recipe that produced the bundles shipped so far (copied
from the ``build/wasm_eh`` CMake cache), installs the artifact into every
directory in the manifest, and records the commit it was built from. The
submodule commit is restored afterwards, whatever happens.

The build path had not been exercised end-to-end when it was written (the
wasm-parity lane does not rebuild binaries); ``--dry-run`` prints the plan.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from fhir4ds.operations.tests.wasm_parity import shipped_bundles  # noqa: E402

# Copied from extensions/cql/build/wasm_eh/CMakeCache.txt, the configuration
# that produced the bundles shipped so far.
CONFIGURE_FLAGS = (
    "-DCMAKE_BUILD_TYPE=Release",
    "-DBUILD_MAIN_DUCKDB_LIBRARY=ON",
    "-DBUILD_EXTENSIONS_ONLY=1",
    "-DEXTENSION_STATIC_BUILD=1",
    "-DBUILD_UNITTESTS=ON",
    "-DBUILD_SHELL=ON",
    "-DBUILD_COMPLETE_EXTENSION_SET=ON",
    "-DBUILD_TESTING=ON",
    "-DENABLE_EXTENSION_AUTOINSTALL=0",
    "-DENABLE_EXTENSION_AUTOLOADING=0",
    "-DENABLE_SANITIZER=ON",
    "-DENABLE_UBSAN=ON",
    "-DENABLE_JEMALLOC=ON",
    "-DENABLE_THREAD_SANITIZER=OFF",
    '-DCMAKE_CXX_FLAGS=-fwasm-exceptions -DWEBDB_FAST_EXCEPTIONS=1',
    # Declare the platform instead of letting the build RUN a compiled probe
    # (duckdb_platform_binary.js) to detect it; the recorded cache sets both.
    "-DDUCKDB_CUSTOM_PLATFORM=wasm_eh",
    "-DDUCKDB_EXPLICIT_PLATFORM=wasm_eh",
)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd}: {result.stderr.strip()}")
    return result.stdout.strip()


def emsdk_root() -> Path:
    """The emscripten SDK: ``$EMSDK``, else the newest ``~/emsdk*``."""
    candidates = [Path(os.environ["EMSDK"])] if os.environ.get("EMSDK") else []
    candidates += sorted(Path.home().glob("emsdk*"), reverse=True)
    for root in candidates:
        if (root / "upstream" / "emscripten" / "emcmake").exists():
            return root
    raise RuntimeError("emscripten SDK not found; set EMSDK (expected ~/emsdk-<version>)")


def verify(require_source: bool = False) -> int:
    manifest = shipped_bundles.load_manifest()
    observed = shipped_bundles.observe(manifest, REPO)
    problems = observed.get("STALE_WASM_BUNDLE", []) + observed.get("WASM_COPY_DRIFT", [])
    for kind in ("STALE_WASM_BUNDLE", "WASM_COPY_DRIFT"):
        for target in observed.get(kind, []):
            print(f"ERROR [{kind}] {target}")
    unknown = observed.get("PROVENANCE_UNKNOWN", [])
    for target in unknown:
        print(f"{'ERROR' if require_source else 'WARNING'} [PROVENANCE_UNKNOWN] {target}")
    if not problems and not unknown:
        print(f"OK: {len(manifest['bundles'])} WASM bundle(s) match {shipped_bundles.MANIFEST.name}")
    return 1 if problems or (require_source and unknown) else 0


def _commands(bundle: dict, abi: str, sdk: Path, jobs: int) -> list[list[str]]:
    """The configure and compile commands. Every value is shell-quoted: a flag value with a
    space (``CMAKE_CXX_FLAGS=-fwasm-exceptions -DWEBDB_FAST_EXCEPTIONS=1``) must reach CMake
    as ONE argument, or the second half silently becomes an unused CMake variable."""
    name = bundle["extension"]
    source, build = REPO / "extensions" / name / "duckdb", REPO / "extensions" / name / "build" / "wasm_eh"
    toolchain = sdk / "upstream" / "emscripten" / "cmake" / "Modules" / "Platform" / "Emscripten.cmake"
    q = shlex.quote
    configure = " ".join(
        [
            "emcmake",
            "cmake",
            "-S",
            q(str(source)),
            "-B",
            q(str(build)),
            q(f"-DCMAKE_TOOLCHAIN_FILE={toolchain}"),
            q(f"-DDUCKDB_EXTENSION_CONFIGS={REPO / 'extensions' / name / 'extension_config.cmake'}"),
            q(f"-DOVERRIDE_GIT_DESCRIBE=v{abi}"),
            *(q(flag) for flag in CONFIGURE_FLAGS),
        ]
    )
    # The emsdk environment is needed for BOTH steps: the link rule calls `emcc` by name.
    env = f"source {q(str(sdk / 'emsdk_env.sh'))} && "
    compile_ = f"make -C {q(str(build))} -j{jobs} {name}_loadable_extension OVERRIDE_GIT_DESCRIBE=v{abi}"
    return [["bash", "-c", env + configure], ["bash", "-c", env + compile_]]


def build(bundle: dict, manifest: dict, *, dry_run: bool, jobs: int) -> dict:
    """Build one bundle; returns its new source record ({} on a dry run)."""
    name, abi = bundle["extension"], manifest["duckdb_abi"]
    submodule = REPO / "extensions" / name / "duckdb"
    initialised = (submodule / "CMakeLists.txt").exists()
    if not initialised and not dry_run:
        raise RuntimeError(f"duckdb submodule not initialised: git submodule update --init extensions/{name}/duckdb")
    sdk = emsdk_root()
    original = _git(submodule, "rev-parse", "HEAD") if initialised else None
    # The build directory is parked so CMake configures from scratch (the emsdk environment
    # supplies CMake 3.22, which has no `--fresh`, and a stale cache makes configure fail
    # or misdirect the build). The previous cache is put back in ``finally``, like the x86
    # twin script does.
    build_dir = REPO / "extensions" / name / "build" / "wasm_eh"
    parked = build_dir.with_name("wasm_eh.parked")
    try:
        if build_dir.exists() and not dry_run:
            if parked.exists():
                shutil.rmtree(parked)
            build_dir.rename(parked)
        if initialised:
            if _git(submodule, "tag", "-l", f"v{abi}") != f"v{abi}":
                _git(submodule, "fetch", "--depth", "1", "origin", f"refs/tags/v{abi}:refs/tags/v{abi}")
            _git(submodule, "checkout", "--detach", f"v{abi}")
        for command in _commands(bundle, abi, sdk, jobs):
            print("  $", " ".join(map(str, command)))
            if not dry_run:
                subprocess.run(command, cwd=REPO, check=True)
        artifact = REPO / "extensions" / name / "build" / "wasm_eh" / "extension" / name / f"{name}.duckdb_extension.wasm"
        for directory in bundle["install"]:
            target = REPO / directory / artifact.name
            print(f"  install {artifact.relative_to(REPO)} -> {target.relative_to(REPO)}")
            if not dry_run:
                if not artifact.exists():
                    raise RuntimeError(f"build did not produce {artifact}")
                shutil.copy2(artifact, target)
    finally:
        if original is not None:
            _git(submodule, "checkout", "--detach", original)
        if parked.exists():
            if build_dir.exists():
                shutil.rmtree(build_dir)
            parked.rename(build_dir)
            print("    restored the previous build cache")
    if dry_run:
        return {}
    return {
        "commit": _git(REPO, "rev-parse", "HEAD"),
        f"{name}_source": _git(REPO, "rev-parse", f"HEAD:extensions/{name}/src"),
        "common_source": _git(REPO, "rev-parse", "HEAD:extensions/common"),
        "duckdb_tag": f"v{abi}",
        "emsdk": sdk.name,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify", action="store_true", help="check the shipped copies (default)")
    action.add_argument("--build", action="store_true", help="rebuild and install bundles")
    parser.add_argument("--extension", action="append", help="limit to these extensions (cql, fhirpath)")
    parser.add_argument("--dry-run", action="store_true", help="with --build: print the plan only")
    parser.add_argument("--require-source", action="store_true", help="with --verify: unknown provenance fails")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="make parallelism (default 4)")
    args = parser.parse_args(argv)

    if not args.build:
        return verify(args.require_source)
    manifest = shipped_bundles.load_manifest()
    for bundle in manifest["bundles"]:
        if args.extension and bundle["extension"] not in args.extension:
            continue
        print(f"{bundle['extension']} @ v{manifest['duckdb_abi']}")
        record = build(bundle, manifest, dry_run=args.dry_run, jobs=args.jobs)
        if record:
            source = REPO / bundle["path"]
            bundle.update(source=record, sha256=shipped_bundles.sha256_of(source), size=source.stat().st_size)
    if not args.dry_run:
        shipped_bundles.MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        return verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
