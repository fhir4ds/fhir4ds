"""Fetch the upstream ONC-derived labeled pair test set (prep only — no gate).

Source: icanbwell/cms-hte-patient-matching-test-set, pinned tag ``0.0.6``
(commit e4cf29e77e5c4e73cba661bffea00fd4fc1543c9, verified 2026-11-17).

Upstream layout findings (tag 0.0.6):

- ``evaluation/fixtures/onc/`` vendors the RAW 2017 ONC Patient Matching
  Algorithm Challenge dataset as nine CSV shards (~120 MB total,
  ``ONC Patient Matching Algorithm Challenge Test Dataset.<A-C ...>.csv``).
  Upstream's own ``onc_loader.py`` documents (session_12, verified
  2026-08-31) that this vendored copy has 1,000,000 rows with 1,000,000
  DISTINCT EnterpriseIDs — it carries NO duplicate-pair answer key, so the
  raw CSVs are an input for pair GENERATION, not a labeled pair set.
- The labeled pair sets are the exported JSONL cases under
  ``evaluation/cases/``: one JSON object per line with
  ``{case_id, source: Patient, target: Patient, expected_match: bool,
  rationale: str, frequency: float}`` where source/target are complete FHIR
  R4 Patient dicts.
  - ``sample_labeled_pairs.jsonl`` (~17 MB) — the sample-dataset export
    (DEFAULT: self-contained pairs, smaller).
  - ``realistic_labeled_pairs.jsonl`` (~37 MB, 30,999 cases) — the
    "realistic dataset" release candidate (households, drift, hard
    negatives; see ``realistic_manifest.json`` upstream for caveats).

This script downloads one artifact's raw.githubusercontent URL into
``fhir4ds/matching/tests/fixtures/onc/`` (gitignored — the data is NOT
committed; a README.md in that directory documents the fetch) and records
provenance in ``onc_fetch_meta.json`` (tag, commit sha, source URL, sha256).

Usage:

    python3 -m fhir4ds.matching.scripts.fetch_onc_test_data            # sample set
    python3 -m fhir4ds.matching.scripts.fetch_onc_test_data --artifact realistic_labeled_pairs.jsonl
    python3 -m fhir4ds.matching.scripts.fetch_onc_test_data --list     # show choices

Loader: :func:`load_onc_pairs` parses a fetched JSONL into
``LabeledPair`` records ready for a future ONC gate (the loader is
exercised end-to-end by a skip-if-not-fetched test).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = [
    "LabeledPair",
    "load_onc_pairs",
    "ONC_FIXTURE_DIR",
    "PINNED_TAG",
    "PINNED_COMMIT",
    "ARTIFACTS",
    "DEFAULT_ARTIFACT",
    "fetch",
]

PINNED_TAG = "0.0.6"
PINNED_COMMIT = "e4cf29e77e5c4e73cba661bffea00fd4fc1543c9"
REPO = "icanbwell/cms-hte-patient-matching-test-set"

# artifact name -> (upstream path, approx size bytes, description)
ARTIFACTS: dict[str, tuple[str, int, str]] = {
    "sample_labeled_pairs.jsonl": (
        "evaluation/cases/sample_labeled_pairs.jsonl",
        17_000_000,
        "labeled pair export of the sample dataset (self-contained pairs)",
    ),
    "realistic_labeled_pairs.jsonl": (
        "evaluation/cases/realistic_labeled_pairs.jsonl",
        37_000_000,
        "labeled pair export of the realistic-dataset release candidate "
        "(30,999 cases; see upstream realistic_manifest.json caveats)",
    ),
}
DEFAULT_ARTIFACT = "sample_labeled_pairs.jsonl"

ONC_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "onc"
)


def _raw_url(upstream_path: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{PINNED_TAG}/{upstream_path}"
    )


@dataclass(frozen=True)
class LabeledPair:
    """One upstream labeled pair: two FHIR Patients + the expected verdict."""

    case_id: str
    source: dict
    target: dict
    expected_match: bool
    rationale: str = ""

    @property
    def pair_key(self) -> tuple[str, str]:
        return tuple(sorted((self.source["id"], self.target["id"])))  # type: ignore[return-value]


def load_onc_pairs(path: Path | str) -> list[LabeledPair]:
    """Load a fetched upstream ``*_labeled_pairs.jsonl`` into LabeledPairs.

    Raises ValueError (naming the line) on malformed records so a truncated
    or wrong-format file fails loudly instead of loading silently empty.
    """
    pairs: list[LabeledPair] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                pair = LabeledPair(
                    case_id=rec["case_id"],
                    source=rec["source"],
                    target=rec["target"],
                    expected_match=bool(rec["expected_match"]),
                    rationale=rec.get("rationale", ""),
                )
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"{path}:{lineno}: malformed pair record ({exc})") from exc
            if pair.source.get("resourceType") != "Patient" or pair.target.get("resourceType") != "Patient":
                raise ValueError(f"{path}:{lineno}: source/target are not Patient resources")
            if "id" not in pair.source or "id" not in pair.target:
                raise ValueError(f"{path}:{lineno}: pair resource missing id")
            pairs.append(pair)
    if not pairs:
        raise ValueError(f"{path}: no pair records found (wrong file or empty fetch?)")
    return pairs


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(artifact: str = DEFAULT_ARTIFACT, dest_dir: Optional[Path] = None) -> Path:
    """Download one pinned artifact into the gitignored fixture dir."""
    if artifact not in ARTIFACTS:
        raise SystemExit(
            f"unknown artifact {artifact!r}; choose one of {sorted(ARTIFACTS)}"
        )
    upstream_path, approx_size, _desc = ARTIFACTS[artifact]
    dest_dir = Path(dest_dir) if dest_dir is not None else ONC_FIXTURE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / artifact
    url = _raw_url(upstream_path)
    print(f"fetching {url} (~{approx_size // 1_000_000} MB) -> {dest}")
    with urllib.request.urlopen(url) as response, open(dest, "wb") as out:  # noqa: S310 (pinned https URL)
        shutil.copyfileobj(response, out)
    meta = {
        "artifact": artifact,
        "repo": REPO,
        "tag": PINNED_TAG,
        "commit": PINNED_COMMIT,
        "url": url,
        "sha256": _sha256(dest),
        "bytes": dest.stat().st_size,
    }
    meta_path = dest_dir / "onc_fetch_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"saved {meta['bytes']} bytes (sha256 {meta['sha256'][:16]}...)")
    print(f"provenance -> {meta_path}")
    return dest


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--artifact",
        default=DEFAULT_ARTIFACT,
        choices=sorted(ARTIFACTS),
        help=f"which upstream labeled-pair export to fetch (default: {DEFAULT_ARTIFACT})",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list available artifacts and exit",
    )
    args = parser.parse_args(argv)
    if args.list:
        for name in sorted(ARTIFACTS):
            path, size, desc = ARTIFACTS[name]
            print(f"{name}  (~{size // 1_000_000} MB)  {desc}\n    upstream: {path}")
        return 0
    fetch(args.artifact)
    return 0


if __name__ == "__main__":
    sys.exit(main())
