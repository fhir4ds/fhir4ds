"""ONC 2017 real-corpus precision/recall gate (AMUX-134).

REAL-DATA MEASUREMENT, not a by-construction pin: the full evaluation runs
against the fetched upstream labeled pairs and the gate is a
regression-vs-baseline check (tolerance ``TOLERANCE``), never an absolute
threshold — imperfect real-world recall is information recorded in
``evaluation/ONC_RESULTS.md``, not a suite failure.

Skips cleanly when the gitignored fixture has not been fetched
(``python3 -m fhir4ds.matching.scripts.fetch_onc_test_data``).
"""

from __future__ import annotations

import pytest

from fhir4ds.matching.evaluation.onc_gate import (
    ONC_PAIRS_PATH,
    TOLERANCE,
    ONCMetrics,
    assert_no_regression,
    evaluate_onc_pairs,
    load_onc_baseline,
    rationale_family,
)
from fhir4ds.matching.scripts.fetch_onc_test_data import load_onc_pairs

pytestmark = pytest.mark.skipif(
    not ONC_PAIRS_PATH.exists(),
    reason=f"ONC fixture not fetched — run "
    f"`python3 -m fhir4ds.matching.scripts.fetch_onc_test_data` to populate "
    f"{ONC_PAIRS_PATH}",
)


def _sliced_pairs(stride: int = 500) -> list:
    """Deterministic thin slice of the full set (keeps both label classes)."""
    pairs = load_onc_pairs(ONC_PAIRS_PATH)
    slice_ = pairs[::stride]
    assert any(p.expected_match for p in slice_)
    assert any(not p.expected_match for p in slice_)
    return slice_


# ---------------------------------------------------------------------------
# Fast harness-mechanics tests (small deterministic slice, real engine)
# ---------------------------------------------------------------------------


def test_onc_small_slice_end_to_end():
    """The isolated-pair evaluation runs over a real slice and the math is
    internally consistent (confusion-matrix totals == case count)."""
    metrics = evaluate_onc_pairs(_sliced_pairs())
    assert metrics.cases == (
        metrics.true_positives
        + metrics.false_positives
        + metrics.false_negatives
        + metrics.true_negatives
    )
    assert metrics.positives == metrics.true_positives + metrics.false_negatives
    assert metrics.negatives == metrics.true_negatives + metrics.false_positives
    if metrics.true_positives + metrics.false_positives:
        assert metrics.precision == pytest.approx(
            metrics.true_positives
            / (metrics.true_positives + metrics.false_positives)
        )
    if metrics.true_positives + metrics.false_negatives:
        assert metrics.recall == pytest.approx(
            metrics.true_positives
            / (metrics.true_positives + metrics.false_negatives)
        )
    assert metrics.crash_count == 0


def test_onc_isolation_leaves_no_leftover_rows():
    """Shared-connection isolation contract: after evaluation the index is
    empty (every pair's rows were deleted, so no pair ever saw another
    pair's patients as candidates)."""
    import duckdb

    from fhir4ds.matching.store import create_matching_tables

    conn = duckdb.connect()
    create_matching_tables(conn)
    evaluate_onc_pairs(_sliced_pairs(), conn=conn)
    leftover = conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0]
    assert leftover == 0, f"{leftover} rows leaked across pair boundaries"
    conn.close()


def test_rationale_family_grouping():
    assert rationale_family("fuzzy_variant/given_nickname") == "fuzzy_variant"
    assert rationale_family("normalization_edge_case/diacritic") == (
        "normalization_edge_case"
    )
    assert (
        rationale_family("compound_variant (mutations=family_typo,given_abbreviate)")
        == "compound_variant"
    )
    assert rationale_family("marriage_variant") == "marriage_variant"


def test_regression_gate_tolerance_semantics():
    """The gate allows drift up to TOLERANCE and fails beyond it."""
    baseline = {
        "cases": 100,
        "precision": 0.99,
        "recall": 0.80,
        "crash_count": 0,
    }
    ok = ONCMetrics(
        precision=0.99 - TOLERANCE,
        recall=0.80 - TOLERANCE + 0.001,
        f1=0.0,
        cases=100,
        positives=90,
        negatives=10,
        true_positives=0,
        false_positives=0,
        false_negatives=0,
        true_negatives=0,
        ambiguous_on_positive=0,
        ambiguous_on_negative=0,
        crash_count=0,
        elapsed_seconds=0.0,
    )
    assert_no_regression(ok, baseline)  # within tolerance -> pass

    for name, value in (("precision", 0.90), ("recall", 0.70)):
        bad = ONCMetrics(**{**ok.__dict__, name: value})
        with pytest.raises(AssertionError, match=name):
            assert_no_regression(bad, baseline)

    # fixture size change -> baseline is stale, must fail loudly
    resized = ONCMetrics(**{**ok.__dict__, "cases": 42})
    with pytest.raises(AssertionError, match="changed size"):
        assert_no_regression(resized, baseline)

    # new engine crashes on real data shapes -> regression
    crashing = ONCMetrics(**{**ok.__dict__, "crash_count": 3})
    with pytest.raises(AssertionError, match="crashes"):
        assert_no_regression(crashing, baseline)


# ---------------------------------------------------------------------------
# The gate: full-set measurement vs committed baseline (slow: ~3 min)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_onc_real_corpus_regression_gate():
    """Full 14,295-pair ONC evaluation must not regress beyond TOLERANCE
    against evaluation/onc_baseline.json (crashes and size changes also
    fail). Absolute performance is recorded, not asserted."""
    from fhir4ds.matching.evaluation.onc_gate import evaluate_onc_fixture

    metrics = evaluate_onc_fixture()
    baseline = load_onc_baseline()
    assert_no_regression(metrics, baseline, TOLERANCE)
