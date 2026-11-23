#!/usr/bin/env python3
"""FHIR4-20 P5 benchmark: the adopt/no-adopt referee (FDD §4).

Two measurements, both required for adoption:

1. **ONC real-corpus gate** (14,295 pairs) run twice — with the E-rules
   active (default) and without (``use_embedding=False``) — reporting
   P / R / FP counts and wall clock against the committed baseline.
2. **Transliteration-heavy held-out set** built with the realism harness
   (``CorruptionConfig(profile_weights={"name_transliteration": 1.0})``
   over a realisticized synthetic corpus), pure and stacked (0.3 stack
   probability with dob_shift/name_typos), evaluated under both rule
   tables.

Prints the decision table with the FDD §4 bar applied:
translit recall >= 0.70 (and +30pp over baseline), ONC precision stays
1.0000 (zero new FP = automatic NO-ADOPT), ONC recall not degraded,
wall clock <= +20 %.

Seeds (documented for reproducibility): ONC runs are deterministic;
translit corpus seed 20261121 / injection seeds 20261122 (pure) and
20261123 (stacked).

Usage:
    python3 scripts/bench_name_embedding.py [--quick]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from fhir4ds.matching.corpus import match_corpus  # noqa: E402
from fhir4ds.matching.engine import match_patient  # noqa: E402
from fhir4ds.matching.evaluation import onc_gate  # noqa: E402
from fhir4ds.matching.rules import (  # noqa: E402
    CATEGORY1_RULES,
    patient_rules_with_embedding,
)
from fhir4ds.matching.scripts.fetch_onc_test_data import (  # noqa: E402
    load_onc_pairs,
)
from fhir4ds.matching.store import (  # noqa: E402
    create_matching_tables,
    index_patient,
)
from fhir4ds.realism.corrupt import (  # noqa: E402
    CorruptionConfig,
    TRANSLITERATION_GROUPS,
    _FAMILY_POOL,
    inject_duplicates,
)

import duckdb  # noqa: E402

CORPUS_SEED = 20261121
INJECT_SEED_PURE = 20261122
INJECT_SEED_STACK = 20261123
N_BASE_PATIENTS = 400
GOLD_TARGET = 300  # num_patients cap for injection

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from train_name_embedding import SEED  # noqa: E402  (documentation parity)


# ---------------------------------------------------------------------------
# part A — ONC gate with / without E-rules
# ---------------------------------------------------------------------------

def run_onc() -> dict:
    pairs = load_onc_pairs(onc_gate.ONC_PAIRS_PATH)
    baseline = onc_gate.load_onc_baseline()

    # WITH embedding (default rules table)
    m_with = onc_gate.evaluate_onc_pairs(list(pairs))

    # WITHOUT embedding: route match_patient through use_embedding=False
    real_match_patient = onc_gate.match_patient

    def _legacy(conn, patient, **kw):
        kw.setdefault("use_embedding", False)
        return real_match_patient(conn, patient, **kw)

    onc_gate.match_patient = _legacy
    try:
        m_without = onc_gate.evaluate_onc_pairs(list(pairs))
    finally:
        onc_gate.match_patient = real_match_patient

    return {
        "baseline": {k: baseline[k] for k in
                     ("precision", "recall", "false_positives",
                      "false_negatives")},
        "without_embedding": {
            "precision": m_without.precision,
            "recall": m_without.recall,
            "false_positives": m_without.false_positives,
            "false_negatives": m_without.false_negatives,
            "elapsed_seconds": m_without.elapsed_seconds,
        },
        "with_embedding": {
            "precision": m_with.precision,
            "recall": m_with.recall,
            "false_positives": m_with.false_positives,
            "false_negatives": m_with.false_negatives,
            "elapsed_seconds": m_with.elapsed_seconds,
            "fn_by_family": m_with.fn_by_family(),
            "family_totals": m_with.family_totals(),
            "fp_by_rationale": m_with.fp_by_rationale,
        },
        "recall_delta": m_with.recall - m_without.recall,
        "new_false_positives": m_with.false_positives - m_without.false_positives,
        "wallclock_ratio": (m_with.elapsed_seconds / m_without.elapsed_seconds
                            if m_without.elapsed_seconds else None),
    }


# ---------------------------------------------------------------------------
# part B — transliteration-heavy held-out set
# ---------------------------------------------------------------------------

def _base_corpus() -> list[dict]:
    """Realisticized synthetic patients: given names drawn 70 % from the
    transliteration tables (so the profile can fire) / 30 % from nickname
    formal names; families from the realism pool; unique DOB / SSN4 /
    phone / address per patient."""
    from fhir4ds.matching.normalizers import _NICKNAME_GROUPS
    rng = random.Random(CORPUS_SEED)
    translit = sorted({n for g in TRANSLITERATION_GROUPS for n in g
                       if len(n) >= 3})
    formal = sorted({max(sorted(g), key=len) for g in _NICKNAME_GROUPS})
    streets = ["Elm Street", "Oak Avenue", "Maple Road", "Cedar Lane",
               "Birch Drive", "Pine Court"]
    patients = []
    for i in range(N_BASE_PATIENTS):
        pool = translit if rng.random() < 0.7 else formal
        given = pool[rng.randrange(len(pool))].capitalize()
        family = _FAMILY_POOL[rng.randrange(len(_FAMILY_POOL))]
        year = 1940 + rng.randrange(70)
        month = 1 + rng.randrange(12)
        day = 1 + rng.randrange(28)
        patients.append({
            "resourceType": "Patient",
            "id": f"bench-{i:04d}",
            "name": [{"use": "official", "family": family,
                      "given": [given]}],
            "birthDate": f"{year:04d}-{month:02d}-{day:02d}",
            "telecom": [{"system": "phone",
                         "value": f"555-{100 + i // 100:03d}-{i % 100:04d}",
                         "use": "home"}],
            "address": [{"use": "home",
                         "line": [f"{100 + i} "
                                  f"{streets[i % len(streets)]}"],
                         "city": "Springfield", "state": "IL",
                         "postalCode": f"606{i % 100:02d}"}],
            "identifier": [
                {"type": {"coding": [{"code": "SS"}]},
                 "system": "http://hl7.org/fhir/sid/us-ssn",
                 "value": f"{900000000 + i * 7}"},
            ],
        })
    return patients


def _evaluate_injection(patients: list[dict], gold_pairs: list,
                        rules: list) -> dict:
    conn = duckdb.connect()
    try:
        create_matching_tables(conn)
        for patient in patients:
            index_patient(conn, patient)
        start = time.monotonic()
        match_corpus(conn, f"bench-{id(rules) & 0xffff}", rules=rules)
        elapsed = time.monotonic() - start
        rows = conn.execute(
            "SELECT linkage_id FROM linkage ORDER BY linkage_id"
        ).fetchall()
    finally:
        conn.close()

    def _norm(ref: str) -> str:
        return ref[len("Patient/"):] if ref.startswith("Patient/") else ref

    predicted = {tuple(sorted((_norm(a), _norm(b))))
                 for a, b in (row[0].split("|", 1) for row in rows)}
    gold = {tuple(sorted((p.original_id, p.dup_id))) for p in gold_pairs}
    tp = gold & predicted

    by_profile: dict[str, dict] = {}
    for profile in sorted({p for g in gold_pairs
                           for p in g.profiles_applied}):
        pairs = [g for g in gold_pairs if profile in g.profiles_applied]
        found = sum(1 for g in pairs
                    if tuple(sorted((g.original_id, g.dup_id))) in tp)
        by_profile[profile] = {
            "pairs": len(pairs), "found": found,
            "recall": round(found / len(pairs), 4) if pairs else None,
        }
    return {
        "gold_pairs": len(gold),
        "predicted_pairs": len(predicted),
        "true_positives": len(tp),
        "false_positives": len(predicted - gold),
        "recall": round(len(tp) / len(gold), 4) if gold else None,
        "precision": (round(len(tp) / len(predicted), 4)
                      if predicted else None),
        "per_profile": by_profile,
        "elapsed_seconds": round(elapsed, 2),
    }


def run_translit() -> dict:
    base = _base_corpus()
    out = {}
    for label, seed, stack, weights in (
        ("pure", INJECT_SEED_PURE, 0.0,
         {"name_transliteration": 1.0}),
        ("stacked", INJECT_SEED_STACK, 0.3,
         {"name_transliteration": 1.0, "dob_shift": 1.0,
          "name_typos": 1.0}),
    ):
        injection = inject_duplicates(
            list(base), [],
            CorruptionConfig(
                seed=seed, num_patients=GOLD_TARGET, dups_per_patient=1,
                clean_duplicate_ratio=0.0, stack_probability=stack,
                profile_weights=weights))
        translit_pairs = [g for g in injection.gold_pairs
                          if "name_transliteration" in g.profiles_applied]
        without = _evaluate_injection(
            injection.patients, injection.gold_pairs, CATEGORY1_RULES)
        with_e = _evaluate_injection(
            injection.patients, injection.gold_pairs,
            patient_rules_with_embedding())
        t_without = next(
            (v for k, v in without["per_profile"].items()
             if k == "name_transliteration"), None)
        t_with = next(
            (v for k, v in with_e["per_profile"].items()
             if k == "name_transliteration"), None)
        out[label] = {
            "gold_pairs": len(injection.gold_pairs),
            "translit_pairs": len(translit_pairs),
            "without_embedding": without,
            "with_embedding": with_e,
            "translit_recall_without": (t_without or {}).get("recall"),
            "translit_recall_with": (t_with or {}).get("recall"),
        }
    return out


# ---------------------------------------------------------------------------
# decision
# ---------------------------------------------------------------------------

def decide(onc: dict, translit: dict) -> dict:
    pure = translit["pure"]
    r_base = pure["translit_recall_without"]
    r_e = pure["translit_recall_with"]
    criteria = {
        "translit_recall_ge_0.70": {
            "value": r_e, "pass": r_e is not None and r_e >= 0.70},
        "translit_gain_ge_30pp": {
            "value": (round(r_e - r_base, 4)
                      if r_e is not None and r_base is not None else None),
            "pass": (r_e is not None and r_base is not None
                     and r_e - r_base >= 0.30)},
        "onc_precision_1.0000": {
            "value": onc["with_embedding"]["precision"],
            "pass": onc["with_embedding"]["precision"] == 1.0
            and onc["new_false_positives"] == 0},
        "onc_recall_not_degraded": {
            "value": onc["recall_delta"],
            "pass": onc["recall_delta"] >= 0},
        "wallclock_le_plus20pct": {
            "value": onc["wallclock_ratio"],
            "pass": (onc["wallclock_ratio"] is not None
                     and onc["wallclock_ratio"] <= 1.20)},
    }
    adopt = all(c["pass"] for c in criteria.values())
    partial = (not adopt and r_e is not None and 0.40 <= r_e < 0.70)
    return {
        "criteria": criteria,
        "verdict": "ADOPT" if adopt else
                   ("SHIP-DISABLED (partial 0.40-0.70)" if partial
                    else "NO-ADOPT"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-onc", action="store_true")
    args = parser.parse_args(argv)

    onc = {"skipped": True}
    if not args.skip_onc:
        print("== ONC gate (with / without E-rules) ==")
        onc = run_onc()
        print(json.dumps({k: v for k, v in onc.items()
                          if k not in ("with_embedding",)}, indent=2))

    print("== transliteration held-out benchmark ==")
    translit = run_translit()
    print(json.dumps(translit, indent=2))

    decision = decide(onc, translit)
    print("== DECISION ==")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
