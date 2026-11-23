#!/usr/bin/env python3
"""FHIR4-20 P4: calibrate the name-embedding distance bands (FDD §3.2).

Measures the REAL distance histograms and replaces the placeholder band
edges + u-values pinned in ``fhir4ds/matching/rules.py`` and the artifact
manifest:

- **negative (calibration) histogram** — P(distinct-name pair lands in
  this band or tighter), cumulative from tight outward, over (i) a seeded
  ~1M-pair sample of the ONC-corpus given-name pool (names only — the ONC
  corpus is never used for training) and (ii) the manufactured hard
  stratum (cross nickname/transliteration-group pairs with Damerau-
  Levenshtein distance <= 2, corrupt.py groups);
- **positive (calibration) histogram** — P(equivalent-name pair lands in
  each band), over the held-out (by-group 10 %) split of the training
  pairs, so calibration sees held-out NAMES, not held-out spellings.

Band edges are searched on a grid to meet the FDD §3.2 v1 capture targets
(tight >= 0.35, tight+mid >= 0.70, all >= 0.85 of calibration positives)
with the SMALLEST edge that satisfies each cumulative target (minimizing
the band's u-value at the required capture). U-values are the cumulative
negative rates at the chosen edges, rounded UP to 2 significant digits.

Budget discipline (FDD §3.2): a band whose u-value cannot appear in an
approvable rule product (loose-u x weakest companion field vs the 2e-12
Category-1 approval threshold) is shipped in NO rule — the band list is
truncated at the last approvable band.

Usage:
    python3 scripts/calibrate_name_embedding.py            # measure + report
    python3 scripts/calibrate_name_embedding.py --apply    # + write rules.py
                                                          #   constants and
                                                          #   the artifact
                                                          #   manifest
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from fhir4ds.matching import name_embedding  # noqa: E402
from fhir4ds.matching.engine import EMBED  # noqa: E402
from fhir4ds.matching.rules import (  # noqa: E402
    FIELD_U_PROBS,
    PATIENT_RULES_WITH_EMBEDDING,
)
from fhir4ds.matching.scripts.fetch_onc_test_data import (  # noqa: E402
    load_onc_pairs,
)
from fhir4ds.realism.corrupt import (  # noqa: E402
    TRANSLITERATION_GROUPS,
    _dl_distance_bounded,
)
from fhir4ds.matching.normalizers import _NICKNAME_GROUPS  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from train_name_embedding import (  # noqa: E402
    SEED,
    TrainingData,
    _savez_deterministic,
    generate_training_data,
)

ONC_PAIRS_PATH = (
    REPO_ROOT / "fhir4ds" / "matching" / "tests" / "fixtures" / "onc"
    / "sample_labeled_pairs.jsonl"
)
RULES_PATH = REPO_ROOT / "fhir4ds" / "matching" / "rules.py"
ARTIFACT_PATH = (
    REPO_ROOT / "fhir4ds" / "matching" / "artifacts" / "name_embed_v1.npz"
)

CAL_SEED = SEED + 1          # distinct from the trainer seed, fixed
ONC_PAIR_SAMPLE = 1_000_000  # FDD §3.2: ~1M sampled pairs
EDGE_GRID = [round(0.01 * i, 3) for i in range(1, 61)]  # 0.01 .. 0.60
CAPTURE_TARGETS = {"tight": 0.35, "mid": 0.70, "loose": 0.85}  # FDD v1
APPROVAL_P = 2e-12  # Category-1 approval threshold (rules.py slice-2 note)


# ---------------------------------------------------------------------------
# histogram sources
# ---------------------------------------------------------------------------

def onc_given_names() -> list[str]:
    """Unique normalized given-name tokens of the ONC pair corpus."""
    pairs = load_onc_pairs(ONC_PAIRS_PATH)
    names: set[str] = set()
    for pair in pairs:
        for patient in (pair.source, pair.target):
            for entry in patient.get("name") or []:
                if not isinstance(entry, dict):
                    continue
                given = entry.get("given") or []
                if isinstance(given, str):
                    given = [given]
                for token in given:
                    if isinstance(token, str):
                        norm = name_embedding._normalize(token)
                        if len(norm.replace(" ", "")) >= 2:
                            names.add(norm.strip())
    return sorted(names)


def hard_negative_pairs() -> list[tuple[str, str]]:
    """Cross-group DL<=2 distinct-name pairs (the trainer's hard stratum,
    recomputed deterministically — corrupt.py groups only)."""
    local = sorted({n for g in (*_NICKNAME_GROUPS, *TRANSLITERATION_GROUPS)
                    for n in g})
    same_group: dict[frozenset[str], None] = {}
    out: list[tuple[str, str]] = []
    for i, a in enumerate(local):
        for b in local[i + 1:]:
            if _dl_distance_bounded(a, b, 2) > 2:
                continue
            key = frozenset({a, b})
            if key in same_group:
                continue
            shared = False
            for group in (*_NICKNAME_GROUPS, *TRANSLITERATION_GROUPS):
                if a in group and b in group:
                    shared = True
                    break
            if not shared:
                out.append((a, b))
    return sorted(out)[:5000]


def _distances(pairs: list[tuple[str, str]]) -> list[float]:
    cache: dict[str, object] = {}

    def vec(name: str):
        if name not in cache:
            cache[name] = name_embedding.embed(name)
        return cache[name]

    import numpy as np
    out = []
    for a, b in pairs:
        va, vb = vec(a), vec(b)
        dot = float(np.clip(va @ vb, -1.0, 1.0))
        out.append(1.0 - dot)
    return out


def _pair_distances_matrix(pool: list[str], count: int,
                           seed: int) -> list[float]:
    """Vectorized sampled distinct-pair distances over a name pool."""
    import numpy as np
    vecs = np.stack([name_embedding.embed(n) for n in pool])
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    rng = random.Random(seed)
    n = len(pool)
    ia = np.fromiter((rng.randrange(n) for _ in range(count)),
                     dtype=np.int64, count=count)
    ib = np.fromiter((rng.randrange(n) for _ in range(count)),
                     dtype=np.int64, count=count)
    keep = ia != ib
    ia, ib = ia[keep], ib[keep]
    dots = np.clip((vecs[ia] * vecs[ib]).sum(axis=1), -1.0, 1.0)
    return (1.0 - dots).tolist()


# ---------------------------------------------------------------------------
# band search
# ---------------------------------------------------------------------------

def _cum_capture(pos: list[float], edge: float) -> float:
    if not pos:
        return 0.0
    return sum(1 for d in pos if d <= edge) / len(pos)


def _cum_negative(neg: list[float], edge: float) -> float:
    if not neg:
        return 0.0
    return sum(1 for d in neg if d <= edge) / len(neg)


def search_bands(pos: list[float], neg: list[float]) -> dict:
    """Smallest edge meeting each cumulative capture target."""
    edges: dict[str, float] = {}
    for band in ("tight", "mid", "loose"):
        target = CAPTURE_TARGETS[band]
        edge = next((e for e in EDGE_GRID
                     if _cum_capture(pos, e) >= target), None)
        if edge is None:
            break
        edges[band] = edge
    cumulative = {b: _cum_negative(neg, e) for b, e in edges.items()}
    return {"edges": edges, "cumulative_u_raw": cumulative}


def _round_up_2sig(x: float) -> float:
    if x <= 0:
        return 0.0
    import math
    exp = math.floor(math.log10(x))
    factor = 10 ** (1 - exp)
    return math.ceil(x * factor) / factor


def approvable_bands(edges: dict, u_values: dict) -> tuple[dict, list[str], dict]:
    """Per-RULE band truncation under the 2e-12 approval threshold.

    A band that cannot appear in an approvable rule product for a given
    rule ships in NO rule (FDD §3.2 discipline) — but approvability is a
    per-rule product (E2's phone companion is 100x stronger than E1's
    ssn4, and E3 squares the band u), so the truncation is applied per
    rule in ``rules.embedding_rules`` rather than globally. This function
    reports which bands each E-rule keeps.

    Returns (kept_by_rule, globally_dropped, kept_edges). Bands are
    cumulative: a rule's kept list is always a tight-anchored prefix.
    """
    kept_by_rule: dict[str, list[str]] = {}
    order = [b for b in ("tight", "mid", "loose") if b in edges]
    for rule in PATIENT_RULES_WITH_EMBEDDING:
        if rule.rule_id not in ("E1", "E2", "E3"):
            continue
        embed_fields = [f for f, m in rule.fields if m == EMBED]
        companion = 1.0
        for fname, mode in rule.fields:
            if mode != EMBED:
                companion *= FIELD_U_PROBS[fname][0]
        kept: list[str] = []
        for band in order:
            if u_values[band] ** len(embed_fields) * companion > APPROVAL_P:
                break
            kept.append(band)
        kept_by_rule[rule.rule_id] = kept
    # A band dropped by EVERY rule is globally dead (reported, never
    # pinned); the global table keeps all measured bands because edges
    # are shared across rules.
    globally_dropped = [
        b for b in order if not any(b in k for k in kept_by_rule.values())
    ]
    return kept_by_rule, globally_dropped, {b: edges[b] for b in order}


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def _patch_rules_py(edges: dict, u_values: dict) -> None:
    text = RULES_PATH.read_text(encoding="utf-8")
    edges_lit = "{" + ", ".join(
        f'"{b}": {e!r}' for b, e in edges.items()) + "}"
    u_lit = "(\n    " + ",\n    ".join(
        f'("{b}", {u!r})' for b, u in u_values.items()) + ",\n)"
    text = re.sub(
        r"BAND_U_VALUES: tuple\[tuple\[str, float\], \.\.\.\] = \([^)]*\)",
        f"BAND_U_VALUES: tuple[tuple[str, float], ...] = {u_lit}",
        text, flags=re.S)
    text = re.sub(
        r"BAND_EDGES: dict\[str, float\] = \{[^}]*\}",
        f"BAND_EDGES: dict[str, float] = {edges_lit}",
        text)
    RULES_PATH.write_text(text, encoding="utf-8")


def _patch_artifact(edges: dict, u_values: dict, report: dict) -> str:
    import hashlib
    import numpy as np
    with np.load(ARTIFACT_PATH, allow_pickle=False) as npz:
        payload = {k: npz[k] for k in npz.files}
    import json as _json
    meta = _json.loads(str(payload["metadata_json"]))
    meta["band_edges"] = dict(edges)
    meta["band_u_values"] = dict(u_values)
    meta["calibrated"] = True
    meta["calibration"] = {
        "script": "scripts/calibrate_name_embedding.py",
        "seed": CAL_SEED,
        "onc_pair_sample": report["onc_pairs_sampled"],
        "hard_negative_pairs": report["hard_negative_pairs"],
        "positive_pairs": report["positive_pairs"],
        "capture_targets": CAPTURE_TARGETS,
        "bands_kept_by_rule": report["bands_kept_by_rule"],
        "bands_dropped_by_every_rule": report["bands_dropped_by_every_rule"],
    }
    meta.pop("note", None)
    payload["metadata_json"] = np.asarray(json.dumps(meta, sort_keys=True))
    _savez_deterministic(ARTIFACT_PATH, payload)
    return hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="write measured values into rules.py and the "
                             "artifact manifest (default: report only)")
    args = parser.parse_args(argv)

    if not name_embedding.artifact_available():
        print("FATAL: artifact unavailable")
        return 2

    print("regenerating training pairs (deterministic, cached pool) ...")
    data: TrainingData = generate_training_data(seed=SEED)
    cal_pos_pairs = [(a, b) for a, b, g in data.positives
                     if data.split_of[g] == "calibration"]
    print(f"calibration positives (held-out groups): {len(cal_pos_pairs)}")

    pool = onc_given_names()
    print(f"ONC given-name pool: {len(pool)} unique names")
    neg_onc = _pair_distances_matrix(pool, ONC_PAIR_SAMPLE, CAL_SEED)
    hard = hard_negative_pairs()
    print(f"hard negative pairs (cross-group DL<=2): {len(hard)}")
    neg_hard = _distances(hard)
    neg = neg_onc + neg_hard
    pos = _distances(cal_pos_pairs)

    result = search_bands(pos, neg)
    edges = result["edges"]
    raw_u = result["cumulative_u_raw"]
    u_round = {b: _round_up_2sig(v) for b, v in raw_u.items()}
    kept_by_rule, globally_dropped, kept_edges = approvable_bands(
        edges, u_round)
    # The global table pins every MEASURED band (edges + u-values are
    # shared across rules); per-rule truncation to approvable bands
    # happens in rules.embedding_rules().

    report = {
        "positive_pairs": len(pos),
        "onc_pairs_sampled": len(neg_onc),
        "hard_negative_pairs": len(neg_hard),
        "positive_histogram": {
            f"{e:.2f}": round(_cum_capture(pos, e), 4) for e in EDGE_GRID[::5]
        },
        "negative_histogram": {
            f"{e:.2f}": round(_cum_negative(neg, e), 5) for e in EDGE_GRID[::5]
        },
        "edges_raw": edges,
        "u_raw": raw_u,
        "u_rounded": u_round,
        "bands_kept_by_rule": kept_by_rule,
        "bands_dropped_by_every_rule": globally_dropped,
        "final_edges": kept_edges,
        "final_u": u_round,
    }
    print(json.dumps(report, indent=2))

    if not args.apply:
        print("\n(dry run — pass --apply to write rules.py + manifest)")
        return 0

    if globally_dropped:
        print(f"NOTE: bands {globally_dropped} dropped by every rule "
              f"(not approvable at {APPROVAL_P:.0e})")
    _patch_rules_py(kept_edges, u_round)
    sha = _patch_artifact(kept_edges, u_round, report)
    print(f"rules.py + artifact manifest updated; artifact sha256={sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
