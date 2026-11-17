"""Golden-set precision/recall harness for patient matching (AMUX-134 gates).

Evaluates the corpus matcher pairwise: index every golden-corpus patient,
run :func:`~fhir4ds.matching.corpus.match_corpus`, and compare the predicted
match-pair set against the corpus labels.

Scoring semantics (gates brief, 2026-11-17):

- a pair counts as *predicted* only when the engine produced a ``match``
  outcome (a Linkage row); ``ambiguous`` outcomes go to human review, so
  they count as NOT matched for recall but never as false positives for
  precision;
- precision = TP / predicted, recall = TP / labeled duplicates;
- every false negative carries a per-miss breakdown: which Category-1 rules
  SHOULD have caught the pair when evaluated in isolation (both directions).
  Pairs no rule can catch are flagged ``uncatchable`` — the golden-set
  generator is responsible for keeping those out of the duplicate labels.

The recorded baseline lives in ``evaluation/baseline.json``; the gate test
fails on regression below the baseline as well as below the absolute floors
(precision >= 0.95, recall >= 0.90).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import duckdb

from ..corpus import _indexed_fields, match_corpus
from ..engine import (
    _candidate_suffixes,
    _fuzzy_rule_pool,
    _rule_candidate_ids,
    _verify_candidate,
)
from ..normalizers import suffix_conflict
from ..rules import CATEGORY1_RULES
from ..store import create_matching_tables, index_patient

__all__ = [
    "GOLDEN_CORPUS_PATH",
    "BASELINE_PATH",
    "GoldenMetrics",
    "load_golden_corpus",
    "catching_rules",
    "evaluate_golden",
    "load_baseline",
]

_PKG_DIR = Path(__file__).resolve().parent
GOLDEN_CORPUS_PATH = _PKG_DIR.parent / "tests" / "fixtures" / "golden_corpus.json"
BASELINE_PATH = _PKG_DIR / "baseline.json"

PRECISION_FLOOR = 0.95
RECALL_FLOOR = 0.90


def load_golden_corpus(path: Optional[Path] = None) -> dict:
    """Load the golden corpus JSON (patients + labeled pairs)."""
    corpus_path = Path(path) if path is not None else GOLDEN_CORPUS_PATH
    return json.loads(corpus_path.read_text(encoding="utf-8"))


def load_baseline(path: Optional[Path] = None) -> dict:
    """Load the recorded metrics baseline."""
    baseline_path = Path(path) if path is not None else BASELINE_PATH
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def catching_rules(
    conn: duckdb.DuckDBPyConnection, patient_id: str, candidate_id: str
) -> list[str]:
    """Rules that would match ``candidate_id`` when ``patient_id`` is
    evaluated against the corpus (self excluded), in isolation.

    This is the per-miss diagnostic: a false-negative pair with a non-empty
    result here SHOULD have been caught — the first-firing-rule order or an
    ambiguity got in the way. An empty result means the current rule set
    genuinely cannot catch the pair.
    """
    create_matching_tables(conn)
    fields = _indexed_fields(conn, patient_id)
    own_suffixes = fields.get("suffix", [])
    caught: list[str] = []
    for rule in CATEGORY1_RULES:
        if any(not fields.get(f) for f, _mode in rule.fields):
            continue
        if rule.exact_fields():
            candidates = _rule_candidate_ids(conn, rule, fields)
        else:
            candidates = _fuzzy_rule_pool(conn, rule, fields)
        if candidate_id not in (candidates - {patient_id}):
            continue
        matched, _fuzzy, _ev = _verify_candidate(conn, rule, fields, candidate_id)
        if matched and not suffix_conflict(
            own_suffixes, _candidate_suffixes(conn, candidate_id)
        ):
            caught.append(rule.rule_id)
    return caught


@dataclass
class GoldenMetrics:
    precision: float
    recall: float
    f1: float
    duplicate_pairs: int
    non_duplicate_pairs: int
    true_positives: int
    false_positive_count: int
    false_negative_count: int
    ambiguous_pair_count: int
    predicted_pair_count: int
    misses: list[dict] = field(default_factory=list)
    false_positives: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "duplicate_pairs": self.duplicate_pairs,
            "non_duplicate_pairs": self.non_duplicate_pairs,
            "true_positives": self.true_positives,
            "false_positive_count": self.false_positive_count,
            "false_negative_count": self.false_negative_count,
            "ambiguous_pair_count": self.ambiguous_pair_count,
            "predicted_pair_count": self.predicted_pair_count,
        }


def _linkage_pairs(conn: duckdb.DuckDBPyConnection) -> set[tuple[str, str]]:
    rows = conn.execute("SELECT linkage_id FROM linkage").fetchall()
    pairs: set[tuple[str, str]] = set()
    for (linkage_id,) in rows:
        left, right = linkage_id.split("|", 1)
        pairs.add(tuple(sorted((left[len("Patient/") :], right[len("Patient/") :]))))
    return pairs


def evaluate_golden(
    conn: duckdb.DuckDBPyConnection,
    corpus: dict,
    run_id: str = "golden-eval",
) -> GoldenMetrics:
    """Index the corpus, run the corpus pass, and score against labels."""
    create_matching_tables(conn)
    for resource in corpus["patients"]:
        index_patient(conn, resource)
    report = match_corpus(conn, run_id)

    labeled = {
        tuple(sorted((p["a"], p["b"]))): p["label"] for p in corpus["pairs"]
    }
    duplicates = {pair for pair, label in labeled.items() if label == "duplicate"}
    predicted = _linkage_pairs(conn)

    tp = len(predicted & duplicates)
    fp_pairs = sorted(predicted - set(labeled))
    fn_pairs = sorted(duplicates - predicted)

    precision = (tp / len(predicted)) if predicted else 1.0
    recall = (tp / len(duplicates)) if duplicates else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    misses: list[dict] = []
    for pair in fn_pairs:
        rules = sorted(
            set(
                catching_rules(conn, pair[0], pair[1])
                + catching_rules(conn, pair[1], pair[0])
            )
        )
        misses.append(
            {
                "pair": list(pair),
                "kind": next(
                    p["kind"] for p in corpus["pairs"] if tuple(sorted((p["a"], p["b"]))) == pair
                ),
                "would_catch": rules,
                "classification": "rule_ordering_or_ambiguity" if rules else "uncatchable",
            }
        )
    false_positives = [
        {"pair": list(pair), "label": labeled.get(pair, "unlabeled")}
        for pair in fp_pairs
    ]

    return GoldenMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        duplicate_pairs=len(duplicates),
        non_duplicate_pairs=len(labeled) - len(duplicates),
        true_positives=tp,
        false_positive_count=len(fp_pairs),
        false_negative_count=len(fn_pairs),
        ambiguous_pair_count=report.ambiguous_outcomes,
        predicted_pair_count=len(predicted),
        misses=misses,
        false_positives=false_positives,
    )
