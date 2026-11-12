#!/usr/bin/env python3
"""Build or verify the bundled DuckDB extension for every ABI slot.

Why this exists
---------------
The bundled binaries are ABI-specific and DuckDB selects one purely by filename
suffix. Two failure modes shipped before this script existed, both silent:

1. **Wrong stamp.** DuckDB compares the extension's embedded source-id with the
   client version string EXACTLY. The duckdb submodule here is a shallow clone,
   so `git describe` can fail and DuckDB falls back to stamping the commit hash
   (`d54cbbe3df`) instead of the tag (`v2.0.0`). That binary is rejected by every
   released client — exactly how `cql.duckdb2_extension` shipped unloadable
   while its `fhirpath` sibling, stamped `v2.0.0`, worked on the same wheel.
2. **Cross-ABI overwrite.** A rebuild wrote the 1.5.6 artifact into BOTH cql
   slots, so native CQL could not load on 1.5.5 at all.

Every build therefore pins `OVERRIDE_GIT_DESCRIBE=<tag>` (the supported knob —
it makes the tag authoritative instead of a shallow `git describe`), then
re-reads the produced file and refuses to install it unless the embedded stamp
matches the slot. Slots and their source pins live in one manifest,
`fhir4ds/extension_bundles.json`, shared with the pytest guard so the two can
never disagree.

Usage
-----
    python3 scripts/build_extension_bundles.py --verify
        Check the six bundled files: present, and stamped for their own ABI.
        Fast, no build. Safe in CI and before a release.

    python3 scripts/build_extension_bundles.py --build --abi 2.0.0
        Rebuild every 2.0 slot from its pinned source and the v2.0.0 submodule.

    python3 scripts/build_extension_bundles.py --build --abi 1.5.5 --extension cql
        Rebuild one slot.

    python3 scripts/build_extension_bundles.py --build --abi 2.0.0 --dry-run
        Print the plan (checks, submodule state, command) without building.

State is always restored: extension sources are checked out back to HEAD,
duckdb submodules return to their recorded commit, and parked build caches are
moved back — including on failure or Ctrl-C.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "fhir4ds" / "extension_bundles.json"
METADATA_TAIL_BYTES = 65536


@dataclass(frozen=True)
class Slot:
    extension: str
    abi: str
    suffix: str
    source_pin: str | None

    @property
    def filename(self) -> str:
        return f"{self.extension}{self.suffix}"

    @property
    def path(self) -> Path:
        return (
            REPO_ROOT
            / "fhir4ds"
            / self.extension
            / "duckdb"
            / "extensions"
            / self.filename
        )


def load_slots() -> list[Slot]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        Slot(
            extension=entry["extension"],
            abi=entry["abi"],
            suffix=entry["suffix"],
            source_pin=entry.get("source_pin"),
        )
        for entry in data["slots"]
    ]


def embedded_stamp(path: Path) -> str | None:
    """DuckDB version string the bundle was built against, or None.

    A hash-stamped bundle returns None: it carries no version string at all,
    which is precisely the unloadable state.
    """
    tail = path.read_bytes()[-METADATA_TAIL_BYTES:].decode("latin-1")
    versions = set(re.findall(r"(?<![\w.])v?\d+\.\d+\.\d+(?![\w.])", tail))
    if not versions:
        return None

    def key(v: str) -> tuple[int, ...]:
        return tuple(int(part) for part in v.lstrip("v").split("."))

    return max(versions, key=key).lstrip("v")


def _run(cmd: list[str], cwd: Path | None = None, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd or REPO_ROOT, capture_output=capture, text=True, check=False
    )


def _git(*args: str) -> str:
    result = _run(["git", *args])
    return (result.stdout or "").strip()


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #
def verify(slots: list[Slot]) -> int:
    failures = 0
    for slot in slots:
        if not slot.path.exists():
            print(f"  MISSING  {slot.filename}  (expected the {slot.abi} ABI)")
            failures += 1
            continue
        stamp = embedded_stamp(slot.path)
        if stamp == slot.abi:
            print(f"  ok       {slot.filename:34} stamped {stamp}")
        else:
            print(
                f"  BAD      {slot.filename:34} stamped {stamp!r}, "
                f"filename claims {slot.abi}"
            )
            failures += 1
    if failures:
        print(
            f"\n{failures} slot(s) would not load. Rebuild with:\n"
            f"  python3 scripts/build_extension_bundles.py --build --abi <abi>"
        )
    return 1 if failures else 0


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build_one(slot: Slot, dry_run: bool) -> bool:
    ext = slot.extension
    submodule = REPO_ROOT / "extensions" / ext / "duckdb"
    build_dir = REPO_ROOT / "extensions" / ext / "build" / "release"
    parked = REPO_ROOT / "extensions" / ext / "build" / "release-parked"
    artifact = build_dir / "extension" / ext / f"{ext}.duckdb_extension"

    original_submodule = _git("-C", str(submodule), "rev-parse", "HEAD")
    original_sources_dirty = _git("status", "--porcelain", "--", f"extensions/{ext}/src")

    print(f"\n=== {slot.filename}: {ext} for DuckDB {slot.abi}")
    print(f"    duckdb submodule -> {slot.abi}  (was {original_submodule[:12]})")
    if slot.source_pin:
        print(f"    extension sources -> {slot.source_pin} (not HEAD)")
    print(f"    make release OVERRIDE_GIT_DESCRIBE=v{slot.abi}")

    if dry_run:
        print("    [dry run] no build performed")
        return True

    try:
        if original_sources_dirty:
            print(
                f"    refusing to build: extensions/{ext}/src has uncommitted changes "
                f"({len(original_sources_dirty.splitlines())} file(s)); commit or stash first"
            )
            return False

        if slot.source_pin:
            checkout = _run(["git", "checkout", "-q", slot.source_pin, "--", f"extensions/{ext}/src"])
            if checkout.returncode != 0:
                print(f"    failed to pin sources: {checkout.stderr.strip()[:200]}")
                return False

        checkout = _run(["-C", str(submodule), "checkout", "-q", f"v{slot.abi}"])
        if checkout.returncode != 0:
            checkout = _run(["git", "-C", str(submodule), "checkout", "-q", f"v{slot.abi}"])
            if checkout.returncode != 0:
                print(f"    no v{slot.abi} tag in the duckdb submodule: {checkout.stderr.strip()[:200]}")
                return False

        if build_dir.exists():
            if parked.exists():
                shutil.rmtree(parked)
            build_dir.rename(parked)

        result = subprocess.run(
            [
                "make",
                "release",
                f"-j{__import__('os').cpu_count() or 4}",
                f"OVERRIDE_GIT_DESCRIBE=v{slot.abi}",
            ],
            cwd=REPO_ROOT / "extensions" / ext,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print("    build FAILED; last errors:")
            for line in (result.stderr or result.stdout or "").splitlines():
                if "error:" in line:
                    print("      " + line[:180])
            return False

        if not artifact.exists():
            print(f"    build reported success but produced no {artifact.name}")
            return False

        stamp = embedded_stamp(artifact)
        if stamp != slot.abi:
            print(
                f"    REFUSING to install: built bundle stamped {stamp!r}, "
                f"expected {slot.abi}. DuckDB would reject it."
            )
            return False

        shutil.copy2(artifact, slot.path)
        print(f"    installed {slot.filename} ({artifact.stat().st_size:,} bytes, stamped {stamp})")
        return True
    finally:
        # Restore sources, submodule and the previous build cache no matter what.
        _run(["git", "checkout", "-q", "HEAD", "--", f"extensions/{ext}/src"])
        _run(["git", "-C", str(submodule), "checkout", "-q", original_submodule])
        if parked.exists():
            if build_dir.exists():
                shutil.rmtree(build_dir)
            parked.rename(build_dir)
        print(f"    restored sources, submodule {original_submodule[:12]}, build cache")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify", action="store_true", help="check the bundled stamps (default)")
    parser.add_argument("--build", action="store_true", help="rebuild slots")
    parser.add_argument("--abi", action="append", help="limit to these DuckDB ABIs (e.g. --abi 2.0.0)")
    parser.add_argument("--extension", action="append", help="limit to these extensions (cql, fhirpath)")
    parser.add_argument("--dry-run", action="store_true", help="with --build: print the plan only")
    args = parser.parse_args(argv)

    slots = load_slots()
    selected = [
        slot
        for slot in slots
        if (not args.abi or slot.abi in args.abi)
        and (not args.extension or slot.extension in args.extension)
    ]
    if not selected:
        print("No slots matched the filters.", file=sys.stderr)
        return 2

    if args.build:
        ok = True
        for slot in selected:
            ok = build_one(slot, args.dry_run) and ok
        if not args.dry_run:
            print("\n=== verifying the installed bundles")
            ok = verify(load_slots()) == 0 and ok
        return 0 if ok else 1

    print("=== verifying bundled extension stamps")
    return verify(selected)


if __name__ == "__main__":
    raise SystemExit(main())
