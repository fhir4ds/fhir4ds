"""ONC 2017 real-corpus precision/recall gate (AMUX-134).

Evaluates the matching engine against the upstream ONC-derived labeled pair
set (``tests/fixtures/onc/sample_labeled_pairs.jsonl``, fetched by
``fhir4ds.matching.scripts.fetch_onc_test_data`` — gitignored, so everything
here skips cleanly when the fixture is absent).

Semantics (distinct from the synthetic golden gate):

- **Pairwise evaluation, NOT corpus mode.** Each labeled pair is an isolated
  two-patient decision: index both patients, then match the source patient
  with ``exclude={source_id}`` so the target is the only candidate. This
  mirrors the upstream ONC challenge scoring shape rather than cluster
  formation.
- **Isolation without reconnecting**: one shared connection is reused, but
  both patients' rows are deleted after each decision, so the index contains
  exactly the pair during evaluation (verified equivalent to a fresh
  connection per pair; the shared connection only amortizes setup — measured
  ~2.7 min for the full 14,295-case set vs ~6.5 min fresh-conn).
- **Scoring**: outcome ``match`` (with the target in ``matched_ids``) is the
  predicted positive; ``ambiguous`` counts as NOT matched — a recall miss,
  never a false positive (same convention as the synthetic golden gate).
- **This is a real-data MEASUREMENT, not a by-construction pin.** Real-world
  recall being imperfect is information, not a bug: the committed baseline
  (``onc_baseline.json``) records the numbers, and the gate asserts only
  regression-with-tolerance (precision/recall may not drop more than
  ``TOLERANCE`` below baseline). Absolute floors are deliberately absent.

CLI (prints the numbers, optionally records the baseline):

    python3 -m fhir4ds.matching.evaluation.onc_gate                 # full run report
    python3 -m fhir4ds.matching.evaluation.onc_gate --write-baseline
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import duckdb

from ..store import create_matching_tables, index_patient
from ..engine import match_patient
from ..scripts.fetch_onc_test_data import DEFAULT_ARTIFACT, ONC_FIXTURE_DIR, load_onc_pairs

__all__ = [
    "ONC_PAIRS_PATH",
    "ONC_BASELINE_PATH",
    "TOLERANCE",
    "ONCMetrics",
    "rationale_family",
    "evaluate_onc_pairs",
    "evaluate_onc_fixture",
    "load_onc_baseline",
    "assert_no_regression",
    "main",
]

_PKG_DIR = Path(__file__).resolve().parent
ONC_PAIRS_PATH = ONC_FIXTURE_DIR / DEFAULT_ARTIFACT
ONC_BASELINE_PATH = _PKG_DIR / "onc_baseline.json"

#: Real-data measurement: allow small nondeterminism-free drift, fail on
#: real regressions. Precision/recall may not drop more than this below the
#: recorded baseline.
TOLERANCE = 0.02

# Isolation invariant check period: every N pairs, assert the shared index
# holds no leftover rows (guards the delete-after-decision contract).
_ISOLATION_CHECK_EVERY = 500


def rationale_family(rationale: str) -> str:
    """Group a rationale into its top-level family.

    ``fuzzy_variant/given_nickname`` -> ``fuzzy_variant``;
    ``compound_variant (mutations=...)`` -> ``compound_variant`` (the
    mutation signature is a within-family detail).
    """
    if rationale.startswith("compound_variant"):
        return "compound_variant"
    return rationale.split("/", 1)[0]


@dataclass
class ONCMetrics:
    precision: float
    recall: float
    f1: float
    cases: int
    positives: int
    negatives: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    ambiguous_on_positive: int
    ambiguous_on_negative: int
    crash_count: int
    elapsed_seconds: float
    fn_by_rationale: dict[str, int] = field(default_factory=dict)
    fp_by_rationale: dict[str, int] = field(default_factory=dict)
    rationale_totals: dict[str, int] = field(default_factory=dict)
    crashes: list[dict] = field(default_factory=list)
    misses: list[dict] = field(default_factory=list)

    def fn_by_family(self) -> dict[str, int]:
        fam: Counter = Counter()
        for rationale, count in self.fn_by_rationale.items():
            fam[rationale_family(rationale)] += count
        return dict(fam.most_common())

    def family_totals(self) -> dict[str, int]:
        fam: Counter = Counter()
        for rationale, count in self.rationale_totals.items():
            fam[rationale_family(rationale)] += count
        return dict(fam.most_common())

    def as_dict(self) -> dict:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "cases": self.cases,
            "positives": self.positives,
            "negatives": self.negatives,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "ambiguous_on_positive": self.ambiguous_on_positive,
            "ambiguous_on_negative": self.ambiguous_on_negative,
            "crash_count": self.crash_count,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "fn_by_rationale": self.fn_by_rationale,
            "fp_by_rationale": self.fp_by_rationale,
            "rationale_totals": self.rationale_totals,
        }


def _decide_pair(
    conn: duckdb.DuckDBPyConnection, pair
) -> tuple[str, bool]:
    """Index both patients, match source (self excluded), clean up.

    Returns ``(outcome, predicted_positive)``. Raises on engine errors —
    the caller records them as crashes (real-data shapes may surprise the
    engine; the gate must measure, not die).
    """
    sid, tid = pair.source["id"], pair.target["id"]
    try:
        index_patient(conn, pair.source)
        index_patient(conn, pair.target)
        result = match_patient(conn, pair.source, exclude=frozenset({sid}))
        return result.outcome, result.outcome == "match" and tid in result.matched_ids
    finally:
        conn.execute(
            "DELETE FROM field_values WHERE patient_id IN (?, ?)", [sid, tid]
        )


def evaluate_onc_pairs(
    pairs: list,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> ONCMetrics:
    """Run the isolated-pair evaluation over ``pairs`` (already loaded).

    ``progress(done, total)`` if provided is called every 500 pairs.
    """
    if conn is None:
        conn = duckdb.connect()
    create_matching_tables(conn)

    tp = fp = fn = tn = 0
    amb_pos = amb_neg = 0
    crashes: list[dict] = []
    fn_by_rat: Counter = Counter()
    fp_by_rat: Counter = Counter()
    rat_totals: Counter = Counter()
    misses: list[dict] = []

    start = time.monotonic()
    for i, pair in enumerate(pairs):
        rationale = pair.rationale
        rat_totals[rationale] += 1
        try:
            outcome, predicted = _decide_pair(conn, pair)
        except Exception as exc:  # noqa: BLE001 — record, keep measuring
            outcome, predicted = "error", False
            crashes.append(
                {
                    "case_id": pair.case_id,
                    "rationale": rationale,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        if pair.expected_match:
            if predicted:
                tp += 1
            else:
                fn += 1
                fn_by_rat[rationale] += 1
                misses.append(
                    {
                        "case_id": pair.case_id,
                        "rationale": rationale,
                        "outcome": outcome,
                    }
                )
                if outcome == "ambiguous":
                    amb_pos += 1
        else:
            if predicted:
                fp += 1
                fp_by_rat[rationale] += 1
            else:
                tn += 1
                if outcome == "ambiguous":
                    amb_neg += 1
        if i % _ISOLATION_CHECK_EVERY == 0:
            leftover = conn.execute(
                "SELECT COUNT(*) FROM field_values"
            ).fetchone()[0]
            if leftover:  # pragma: no cover — contract guard
                raise RuntimeError(
                    f"isolation violated: {leftover} leftover field_values "
                    f"rows after pair {pair.case_id}"
                )
            if progress:
                progress(i, len(pairs))
    elapsed = time.monotonic() - start

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return ONCMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        cases=len(pairs),
        positives=tp + fn,
        negatives=fp + tn,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        ambiguous_on_positive=amb_pos,
        ambiguous_on_negative=amb_neg,
        crash_count=len(crashes),
        elapsed_seconds=elapsed,
        fn_by_rationale=dict(fn_by_rat.most_common()),
        fp_by_rationale=dict(fp_by_rat.most_common()),
        rationale_totals=dict(rat_totals),
        crashes=crashes,
        misses=misses,
    )


def evaluate_onc_fixture(
    path: Optional[Path] = None, progress: Optional[Callable[[int, int], None]] = None
) -> ONCMetrics:
    """Load the fetched ONC fixture and evaluate it end to end."""
    return evaluate_onc_pairs(load_onc_pairs(path or ONC_PAIRS_PATH), progress=progress)


def load_onc_baseline(path: Optional[Path] = None) -> dict:
    return json.loads((path or ONC_BASELINE_PATH).read_text(encoding="utf-8"))


def assert_no_regression(
    metrics: ONCMetrics, baseline: dict, tolerance: float = TOLERANCE
) -> None:
    """Gate: the real-data measurement may not regress beyond ``tolerance``.

    Fails (AssertionError naming the drift) when precision or recall drops
    more than ``tolerance`` below the recorded baseline, when the fixture
    changed size (different corpus -> different baseline), or when engine
    crashes appear that the baseline did not have.
    """
    assert metrics.cases == baseline["cases"], (
        f"ONC fixture changed size: {metrics.cases} cases vs baseline "
        f"{baseline['cases']} — re-measure and re-record the baseline"
    )
    for name in ("precision", "recall"):
        measured = getattr(metrics, name)
        allowed = baseline[name] - tolerance
        assert measured >= allowed, (
            f"ONC real-corpus {name} regression: {measured:.4f} < baseline "
            f"{baseline[name]:.4f} - {tolerance:.2f} (floor {allowed:.4f})"
        )
    assert metrics.crash_count <= baseline.get("crash_count", 0), (
        f"engine crashes on ONC data shapes: {metrics.crash_count} "
        f"(baseline {baseline.get('crash_count', 0)}) — "
        f"{[c['error'] for c in metrics.crashes[:3]]}"
    )


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover — CLI
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="record the measured numbers into evaluation/onc_baseline.json",
    )
    args = parser.parse_args(argv)

    def _progress(done: int, total: int) -> None:
        print(f"  {done}/{total}", flush=True)

    metrics = evaluate_onc_fixture(progress=_progress)
    print(
        f"\ncases={metrics.cases} positives={metrics.positives} "
        f"negatives={metrics.negatives} ({metrics.elapsed_seconds:.0f}s)"
    )
    print(
        f"TP={metrics.true_positives} FP={metrics.false_positives} "
        f"FN={metrics.false_negatives} TN={metrics.true_negatives}"
    )
    print(
        f"precision={metrics.precision:.4f} recall={metrics.recall:.4f} "
        f"f1={metrics.f1:.4f} crashes={metrics.crash_count}"
    )
    print("\nfalse negatives by rationale family (misses/total, miss rate):")
    fam_totals = metrics.family_totals()
    for fam, count in metrics.fn_by_family().items():
        total = fam_totals.get(fam, 0)
        print(f"  {count:5d}/{total:5d} ({count / total:6.1%})  {fam}")
    if metrics.false_positives:
        print("\nfalse positives by rationale:")
        for rationale, count in sorted(metrics.fp_by_rationale.items()):
            print(f"  {count:5d}/{metrics.rationale_totals[rationale]:5d}  {rationale}")
    if args.write_baseline:
        ONC_BASELINE_PATH.write_text(
            json.dumps(metrics.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nbaseline written -> {ONC_BASELINE_PATH}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
