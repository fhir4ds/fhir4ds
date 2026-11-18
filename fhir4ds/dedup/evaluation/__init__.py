"""Golden-corpus precision/recall harness for temporal dedup (AMUX-142 gates).

Evaluates :func:`~fhir4ds.dedup.runner.run_dedup` end to end against the
labeled golden corpus (``tests/fixtures/dedup_golden_corpus.json``, generated
by ``scripts/gen_dedup_golden.py``):

- **Pairwise P/R over clusters** (matching-gate convention): a pair is
  predicted-duplicate when the two resources land in the same predicted
  cluster. Positive pairs are all within-``clusters`` label pairs; negative
  pairs are the explicitly labeled hard cases.
- **Precision is a 1.0 TARGET, not a baseline**: ANY false merge — on a
  labeled hard negative or on an unlabeled pair — is a failure to
  investigate, never an accepted baseline dip. The gate asserts
  ``precision == 1.0``.
- **Recall is a recorded baseline with a ±0.02 regression gate**
  (``evaluation/baseline.json``, mirroring the matching
  ``baseline.json``/``onc_baseline.json`` pattern).
- **Survivorship accuracy** = the fraction of labeled clusters (those with a
  determinable ``expectedSurvivorRid``) whose predicted survivor matches the
  label.

The predicted clustering and survivor are read back from the RUNNER's
artifacts (the survivor resource's dedup extension: ``sourceReferences`` and
``survivorRule.survivorRid``), so the gate exercises the full
normalize → partition → escalate → survive → merge surface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import duckdb

from ..runner import DedupRunResult, run_dedup
from ..survivorship import DEDUP_EXTENSION_URL

__all__ = [
    "GOLDEN_CORPUS_PATH",
    "BASELINE_PATH",
    "PRECISION_TARGET",
    "RECALL_TOLERANCE",
    "DedupGoldenMetrics",
    "load_golden_corpus",
    "load_baseline",
    "predicted_clusters",
    "evaluate_dedup_golden",
    "assert_no_regression",
]

_PKG_DIR = Path(__file__).resolve().parent
GOLDEN_CORPUS_PATH = _PKG_DIR.parent / "tests" / "fixtures" / "dedup_golden_corpus.json"
BASELINE_PATH = _PKG_DIR / "baseline.json"

#: Any false merge is a failure to investigate, not a baseline dip.
PRECISION_TARGET = 1.0
#: Recall regression tolerance (mirrors the matching ONC-gate TOLERANCE).
RECALL_TOLERANCE = 0.02


def load_golden_corpus(path: Optional[Path] = None) -> dict:
    """Load the golden corpus JSON (resources + labeled clusters/negatives)."""
    corpus_path = Path(path) if path is not None else GOLDEN_CORPUS_PATH
    return json.loads(corpus_path.read_text(encoding="utf-8"))


def load_baseline(path: Optional[Path] = None) -> dict:
    baseline_path = Path(path) if path is not None else BASELINE_PATH
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def _dedup_extension(survivor: dict) -> Optional[dict]:
    for entry in survivor.get("extension") or []:
        if isinstance(entry, dict) and entry.get("url") == DEDUP_EXTENSION_URL:
            return entry
    return None


def _extension_strings(entry: dict, name: str) -> list[str]:
    for sub in entry.get("extension") or []:
        if sub.get("url") == name:
            if "valueString" in sub:
                return [sub["valueString"]]
            return [
                s["valueString"] for s in sub.get("extension") or []
                if s.get("url") == "sourceReference" and "valueString" in s
            ]
    return []


def _rid(reference: str) -> str:
    return reference.split("/", 1)[1] if "/" in reference else reference


def _survivor_rid(entry: dict) -> Optional[str]:
    for sub in entry.get("extension") or []:
        if sub.get("url") != "survivorRule":
            continue
        for leaf in sub.get("extension") or []:
            if leaf.get("url") == "survivorRid" and "valueString" in leaf:
                return leaf["valueString"]
    return None


def predicted_clusters(result: DedupRunResult) -> list[tuple[list[str], str]]:
    """Predicted ``(member_rids_sorted, survivor_rid)`` per cluster, read back
    from the survivor resources' dedup extensions (the runner's public
    surface), sorted by first member rid."""
    clusters: list[tuple[list[str], str]] = []
    for survivor in result.survivors:
        entry = _dedup_extension(survivor)
        if entry is None:  # pragma: no cover — every survivor carries it
            continue
        members = sorted(_rid(r) for r in _extension_strings(entry, "sourceReferences"))
        clusters.append((members, _survivor_rid(entry)))
    clusters.sort(key=lambda pair: pair[0])
    return clusters


def _pairs(member_lists) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for members in member_lists:
        ordered = sorted(members)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                pairs.add((a, b))
    return pairs


@dataclass
class DedupGoldenMetrics:
    precision: float
    recall: float
    f1: float
    labeled_clusters: int
    labeled_negatives: int
    predicted_cluster_count: int
    positive_pairs: int
    true_positives: int
    false_positive_count: int
    false_negative_count: int
    survivorship_total: int
    survivorship_correct: int
    survivorship_accuracy: float
    misses: list[dict] = field(default_factory=list)
    false_positives: list[dict] = field(default_factory=list)
    survivorship_errors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "labeled_clusters": self.labeled_clusters,
            "labeled_negatives": self.labeled_negatives,
            "predicted_cluster_count": self.predicted_cluster_count,
            "positive_pairs": self.positive_pairs,
            "true_positives": self.true_positives,
            "false_positive_count": self.false_positive_count,
            "false_negative_count": self.false_negative_count,
            "survivorship_total": self.survivorship_total,
            "survivorship_correct": self.survivorship_correct,
            "survivorship_accuracy": self.survivorship_accuracy,
        }


def evaluate_dedup_golden(
    corpus: dict,
    *,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
) -> DedupGoldenMetrics:
    """Run the full dedup pass over the golden corpus and score it."""
    own = conn is None
    if own:
        conn = duckdb.connect()
    try:
        result = run_dedup(corpus["resources"], "dedup-golden-eval", conn=conn)
    finally:
        if own:
            conn.close()

    predicted = predicted_clusters(result)
    predicted_member_sets = [members for members, _ in predicted]
    survivor_by_members = {tuple(members): rid for members, rid in predicted}

    labeled = corpus["clusters"]
    labeled_member_sets = [sorted(c["members"]) for c in labeled]
    expected_survivors = {
        tuple(sorted(c["members"])): c.get("expectedSurvivorRid")
        for c in labeled if c.get("expectedSurvivorRid")
    }
    kind_by_members = {tuple(sorted(c["members"])): c.get("kind", "?")
                       for c in labeled}

    pred_pairs = _pairs(predicted_member_sets)
    pos_pairs = _pairs(labeled_member_sets)
    labeled_negative_pairs = {
        tuple(sorted((n["a"], n["b"]))) for n in corpus["negatives"]
    }
    assert not (pos_pairs & labeled_negative_pairs), (
        "corpus label conflict: pair labeled both duplicate and non-duplicate"
    )

    tp = len(pred_pairs & pos_pairs)
    fp_pairs = sorted(pred_pairs - pos_pairs)
    fn_pairs = sorted(pos_pairs - pred_pairs)
    precision = (tp / len(pred_pairs)) if pred_pairs else 1.0
    recall = (tp / len(pos_pairs)) if pos_pairs else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    negative_kinds: dict[tuple[str, str], str] = {
        tuple(sorted((n["a"], n["b"]))): n.get("kind", "?")
        for n in corpus["negatives"]
    }
    misses = [
        {
            "pair": list(pair),
            "kind": kind_by_members.get(
                next((tuple(m) for m in labeled_member_sets
                      if pair[0] in m and pair[1] in m), ()), "?"),
        }
        for pair in fn_pairs
    ]
    false_positives = [
        {
            "pair": list(pair),
            "label": negative_kinds.get(pair, "unlabeled"),
        }
        for pair in fp_pairs
    ]

    survivorship_total = survivorship_correct = 0
    survivorship_errors: list[dict] = []
    for members, expected in expected_survivors.items():
        predicted_survivor = survivor_by_members.get(members)
        survivorship_total += 1
        if predicted_survivor == expected:
            survivorship_correct += 1
        else:
            survivorship_errors.append({
                "members": list(members),
                "expected": expected,
                "predicted": predicted_survivor,
            })
    survivorship_accuracy = (
        survivorship_correct / survivorship_total if survivorship_total else 1.0
    )

    return DedupGoldenMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        labeled_clusters=len(labeled),
        labeled_negatives=len(labeled_negative_pairs),
        predicted_cluster_count=len(predicted),
        positive_pairs=len(pos_pairs),
        true_positives=tp,
        false_positive_count=len(fp_pairs),
        false_negative_count=len(fn_pairs),
        survivorship_total=survivorship_total,
        survivorship_correct=survivorship_correct,
        survivorship_accuracy=survivorship_accuracy,
        misses=misses,
        false_positives=false_positives,
        survivorship_errors=survivorship_errors,
    )


def assert_no_regression(
    metrics: DedupGoldenMetrics,
    baseline: dict,
    *,
    recall_tolerance: float = RECALL_TOLERANCE,
    precision_target: float = PRECISION_TARGET,
) -> None:
    """Gate: precision is at target (1.0 — any false merge is a failure to
    investigate), recall within tolerance of the recorded baseline, and
    survivorship accuracy at 1.0."""
    assert metrics.precision == precision_target, (
        f"dedup golden precision {metrics.precision:.4f} < target "
        f"{precision_target:.2f}: false merges "
        f"{[fp['pair'] for fp in metrics.false_positives[:5]]} "
        f"(kinds: {sorted({fp['label'] for fp in metrics.false_positives})}) — "
        "investigate every false merge; the golden gate never accepts one"
    )
    allowed = baseline["recall"] - recall_tolerance
    assert metrics.recall >= allowed, (
        f"dedup golden recall regression: {metrics.recall:.4f} < baseline "
        f"{baseline['recall']:.4f} - {recall_tolerance:.2f} (floor {allowed:.4f}); "
        f"misses: {[(m['kind'], m['pair']) for m in metrics.misses[:5]]}"
    )
    assert metrics.survivorship_accuracy == 1.0, (
        f"survivorship accuracy {metrics.survivorship_accuracy:.4f}: "
        f"{metrics.survivorship_errors[:3]}"
    )
    assert baseline.get("false_positive_count", 0) == 0, (
        "baseline records false merges — re-record a clean baseline"
    )
