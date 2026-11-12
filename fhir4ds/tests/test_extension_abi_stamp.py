"""Every bundled extension must be stamped with the ABI its filename claims.

DuckDB validates an extension's embedded source-id against the client's version
string with an EXACT comparison, so a bundle built from the correct source but
stamped with a commit hash instead of the release tag cannot load anywhere.

That is exactly what shipped: `cql.duckdb2_extension` embedded `d54cbbe3df`
(the commit hash) while its sibling `fhirpath.duckdb2_extension` embedded
`v2.0.0` (the tag), and `d54cbbe3df` IS the v2.0.0 tag commit — `git describe`
on it returns `v2.0.0`. So the ABI was fine and only the stamp was wrong, which
meant released-DuckDB-2.0 users silently fell back to Python UDFs:

    The file was built specifically for DuckDB version 'd54cbbe3df' and can
    only be loaded with that version of DuckDB. (this version of DuckDB is 'v2.0.0')

The existing dual-support test only asserted that the bundle files EXIST, so the
stamp bug passed CI. These tests check the stamp itself, for every shipped slot,
without needing that DuckDB line installed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXT_DIRS = (
    REPO_ROOT / "fhir4ds" / "fhirpath" / "duckdb" / "extensions",
    REPO_ROOT / "fhir4ds" / "cql" / "duckdb" / "extensions",
)

# Slots come from the ONE manifest the build script also reads, so the builder
# and this guard can never disagree about which ABI a filename means.
MANIFEST = REPO_ROOT / "fhir4ds" / "extension_bundles.json"
SLOTS = json.loads(MANIFEST.read_text(encoding="utf-8"))["slots"]
EXTENSIONS = ("cql", "fhirpath")

METADATA_TAIL_BYTES = 65536


def _embedded_stamp(path: Path) -> str | None:
    """Return the DuckDB version string the bundle was built against.

    DuckDB appends its metadata trailer at the end of the file; the source-id is
    a plain string there. A bundle built from an untagged checkout embeds a
    commit hash instead, which is indistinguishable from "no stamp" for our
    purposes — both fail the exact-match check against a released client.
    """
    tail = path.read_bytes()[-METADATA_TAIL_BYTES:].decode("latin-1")
    versions = set(re.findall(r"(?<![\w.])v?\d+\.\d+\.\d+(?![\w.])", tail))
    if not versions:
        return None
    # Prefer the highest-looking version if the trailer carries several (older
    # builds embed a compatibility table too).
    def _key(v: str):
        return tuple(int(p) for p in v.lstrip("v").split("."))

    return max(versions, key=_key).lstrip("v")


def _slot_path(extension: str, suffix: str) -> Path:
    return EXT_DIRS[0 if extension == "fhirpath" else 1] / f"{extension}{suffix}"


def _slots() -> list[tuple[Path, str]]:
    return [(_slot_path(s["extension"], s["suffix"]), s["abi"]) for s in SLOTS]


@pytest.mark.parametrize(
    "path,expected",
    [pytest.param(p, e, id=p.name) for p, e in _slots()],
)
def test_bundle_is_stamped_for_its_abi(path: Path, expected: str):
    """A hash-stamped (or mismatched) bundle cannot load in a released client."""
    stamp = _embedded_stamp(path)
    assert stamp == expected, (
        f"{path.name} embeds DuckDB version {stamp!r} but its filename claims the "
        f"{expected} ABI. DuckDB matches this string exactly, so the bundle will "
        f"refuse to load in any released {expected} client and quietly fall back "
        f"to the Python UDFs. Rebuild it from a checkout where `git describe "
        f"--tags` resolves the release tag (not a bare commit hash)."
    )


def test_every_expected_slot_is_present():
    """Missing bundles are a separate failure mode: they disable native silently."""
    for slot in SLOTS:
        path = _slot_path(slot["extension"], slot["suffix"])
        assert path.exists(), (
            f"{path.name} is missing from the wheel; DuckDB {slot['abi']} users "
            f"would silently run the Python fallback."
        )
