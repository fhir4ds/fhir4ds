"""Realism benchmark runner (AMUX-150 follow-on).

Runs the FULL stack over a corpus + injected duplicates:

1. **Matching**: index every Patient (originals + dups + honest
   negatives), run the corpus pass, read the Linkage table as the
   predicted-pair set, and score precision / recall against the gold
   pairs — including per-profile recall (which corruption families does
   the engine miss?).
2. **Dedup**: run the temporal dedup pipeline over the merged clinical
   resource set and report cluster-count sanity, a cross-patient
   cluster-violation check (a cluster spanning two patients would be a
   dedup bug), and the curation-queue composition by kind (the
   real-data AMUX-145 validation surface).
3. **PIQI** (optional, ``run_piqi=True``): materialize the packaged
   views over the merged corpus and evaluate the ``sample`` rubric.

Determinism: same corpus + same arguments -> byte-identical JSON report.
No wall clock, no unseeded RNG; floats are rounded to 6 digits.

CLI::

    python3 -m fhir4ds.realism.benchmark --corpus <dir-or-file> \
        --output-dir <dir> [--seed N] [--num-dup-patients N] \
        [--dups-per-patient N] [--clean-duplicate-ratio F] \
        [--stack-probability F] [--profile-weights JSON] [--piqi]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional, Union

import duckdb

from .corpus import load_corpus
from .corrupt import CorruptionConfig, GoldPair, InjectionResult, inject_duplicates

__all__ = ["run_benchmark", "main", "REPORT_FILENAME", "QUEUE_FILENAME"]

REPORT_FILENAME = "realism_report.json"
_QUEUE_KINDS_DESCRIPTION = (
    "kind counts from the deterministic dedup curation queue")


def _round(x: float) -> float:
    return round(float(x), 6)


def _clinical_patient_id(resource: dict) -> Optional[str]:
    for field_name in ("subject", "patient"):
        holder = resource.get(field_name)
        if isinstance(holder, dict) and isinstance(
                holder.get("reference"), str):
            ref = holder["reference"]
            if ref.startswith("Patient/"):
                return ref[len("Patient/"):]
    return None


def _inject(corpus_path: Union[str, Path], *, seed: int,
            num_dup_patients: Optional[int], dups_per_patient: int,
            clean_duplicate_ratio: float, stack_probability: float,
            profile_weights: Optional[dict], realistic_names: bool,
            rebase_dobs: bool,
            patient_limit: Optional[int]) -> tuple[InjectionResult, dict]:
    resources = load_corpus(corpus_path)
    patients = sorted((r for r in resources
                       if r["resourceType"] == "Patient"),
                      key=lambda r: r["id"])
    clinical = sorted((r for r in resources
                       if r["resourceType"] != "Patient"),
                      key=lambda r: r.get("id", ""))
    if patient_limit is not None:
        patients = patients[:patient_limit]
        keep = {p["id"] for p in patients}
        clinical = [r for r in clinical
                    if _clinical_patient_id(r) in (keep | {None})]
    config = CorruptionConfig(
        seed=seed,
        num_patients=num_dup_patients,
        dups_per_patient=dups_per_patient,
        clean_duplicate_ratio=clean_duplicate_ratio,
        stack_probability=stack_probability,
        profile_weights=profile_weights,
        realistic_names=realistic_names,
        rebase_future_birthdates=rebase_dobs,
    )
    result = inject_duplicates(patients, clinical, config)
    corpus_counts = dict(sorted(Counter(
        r["resourceType"] for r in resources).items()))
    return result, corpus_counts


def _matching_section(injection: InjectionResult) -> dict:
    from fhir4ds.matching.corpus import match_corpus
    from fhir4ds.matching.store import create_matching_tables, index_patient

    conn = duckdb.connect()
    try:
        create_matching_tables(conn)
        for patient in injection.patients:
            index_patient(conn, patient)
        run_id = f"realism-{injection.seed}"
        report = match_corpus(conn, run_id)
        rows = conn.execute(
            "SELECT linkage_id FROM linkage ORDER BY linkage_id").fetchall()
    finally:
        conn.close()

    def _norm(ref: str) -> str:
        return ref[len("Patient/"):] if ref.startswith("Patient/") else ref

    predicted = {tuple(sorted((_norm(a), _norm(b))))
                 for a, b in (row[0].split("|", 1) for row in rows)}
    gold = {tuple(sorted((p.original_id, p.dup_id)))
            for p in injection.gold_pairs}
    tp = gold & predicted
    precision = len(tp) / len(predicted) if predicted else 0.0
    recall = len(tp) / len(gold) if gold else 0.0

    per_profile: dict[str, dict] = {}
    for profile in sorted({p for g in injection.gold_pairs
                           for p in g.profiles_applied}):
        pairs = [g for g in injection.gold_pairs
                 if profile in g.profiles_applied]
        found = sum(1 for g in pairs
                    if tuple(sorted((g.original_id, g.dup_id))) in tp)
        per_profile[profile] = {
            "pairs": len(pairs),
            "found": found,
            "recall": _round(found / len(pairs)) if pairs else None,
        }

    return {
        "patients_indexed": report.patients_evaluated,
        "outcomes": {
            "match": report.match_outcomes,
            "ambiguous": report.ambiguous_outcomes,
            "no_match": report.no_match_outcomes,
        },
        "predicted_pairs": len(predicted),
        "gold_pairs": len(gold),
        "true_positives": len(tp),
        "false_positives": len(predicted - gold),
        "false_negatives": len(gold - predicted),
        "precision": _round(precision),
        "recall": _round(recall),
        "per_profile_recall": {
            k: v["recall"] for k, v in per_profile.items()},
        "per_profile_detail": per_profile,
        "missed_gold_pairs": sorted(
            [list(pair) for pair in (gold - predicted)]),
    }


def _dedup_section(injection: InjectionResult,
                   output_dir: Optional[Path]) -> dict:
    from fhir4ds.dedup import run_dedup
    from fhir4ds.dedup.pipeline import dedup_pass

    resources = injection.clinical
    run_id = f"realism-{injection.seed}"
    try:
        run = run_dedup(resources, run_id,
                        output_dir=str(output_dir) if output_dir else None)
    except Exception as exc:  # a dedup defect is a FINDING, not a crash
        import traceback
        return {
            "input_resources": len(resources),
            "resource_counts": dict(sorted(Counter(
                r.get("resourceType", "?") for r in resources).items())),
            "failed": True,
            "error_type": type(exc).__name__,
            "error": (str(exc) or traceback.format_exc()[-2000:]),
            "note": "dedup pipeline raised on this corpus — root-cause "
                    "report filed; see realism_harness_report.md",
        }
    stats = dict(sorted(run.stats.items()))

    # Cluster sanity via the pure pass: clusters + a cross-patient
    # violation check (a cluster must never span two patient refs).
    try:
        pure = dedup_pass(resources)
    except Exception as exc:  # pragma: no cover - same defect class
        return {
            "input_resources": len(resources),
            "resource_counts": dict(sorted(Counter(
                r.get("resourceType", "?") for r in resources).items())),
            "stats": stats,
            "failed": True,
            "error_type": type(exc).__name__,
            "error": str(exc)[:2000],
            "note": "dedup_pass raised during cluster sanity — root-cause "
                    "report filed; see realism_harness_report.md",
        }
    cross = 0
    for cluster in pure.clusters:
        refs = {m.patient_ref for m in cluster if m.patient_ref}
        if len(refs) > 1:
            cross += 1

    queue_by_kind: dict[str, int] = {}
    if run.curation_queue_path:
        with open(run.curation_queue_path, encoding="utf-8") as handle:
            entries = [json.loads(line) for line in handle if line.strip()]
        queue_by_kind = dict(sorted(
            Counter(e.get("kind", "unknown") for e in entries).items()))

    return {
        "input_resources": len(resources),
        "resource_counts": dict(sorted(Counter(
            r.get("resourceType", "?") for r in resources).items())),
        "stats": stats,
        "clusters": stats.get("clusters", 0),
        "cross_patient_clusters": cross,
        "curation_queue_by_kind": queue_by_kind,
        # filename only (never an absolute path) so report bytes are
        # independent of the output directory
        "curation_queue_file": (
            Path(run.curation_queue_path).name
            if run.curation_queue_path else None),
        "queue_note": _QUEUE_KINDS_DESCRIPTION,
    }


def _piqi_section(injection: InjectionResult) -> dict:
    """Evaluate the packaged 'sample' PIQI rubric over the merged corpus."""
    try:
        from fhir4ds.fhirpath.duckdb import register_fhirpath
        from fhir4ds.piqi import evaluate_rubric, load_piqi_views
    except Exception as exc:  # pragma: no cover - environment-dependent
        return {"available": False, "error": f"import failed: {exc}"}
    conn = duckdb.connect(config={"allow_unsigned_extensions": True})
    try:
        registered = register_fhirpath(conn)
        conn.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
        resources = injection.patients + injection.clinical
        for resource in sorted(resources,
                               key=lambda r: (r["resourceType"], r["id"])):
            conn.execute("INSERT INTO resources VALUES (?)",
                         [json.dumps(resource)])
        load_piqi_views(conn, source_table="resources")
        scorecard = evaluate_rubric(conn, "sample")
        return {
            "available": True,
            "fhirpath_native": bool(registered),
            "scorecard": scorecard.to_dict(),
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    finally:
        conn.close()


def run_benchmark(
    corpus: Union[str, Path],
    *,
    output_dir: Union[str, Path],
    seed: int = 20261120,
    num_dup_patients: Optional[int] = 10,
    dups_per_patient: int = 1,
    clean_duplicate_ratio: float = 0.2,
    stack_probability: float = 0.3,
    profile_weights: Optional[dict] = None,
    realistic_names: bool = False,
    rebase_dobs: bool = False,
    patient_limit: Optional[int] = None,
    run_piqi: bool = False,
    report_path: Optional[Union[str, Path]] = None,
) -> dict:
    """Run the full realism benchmark. Returns the report dict (also
    written as JSON under ``output_dir``).

    ``realistic_names``: replace synthetic MIMIC-style patient names
    (``Patient_<id>`` literals, no given names) with generated realistic
    names before duplicate injection — REQUIRED for name corruption on
    the MIMIC demo corpus, leave off for corpora with real names.
    ``rebase_dobs``: shift future (de-identification-shifted) birthDates
    back by whole centuries so the matcher's date normalization accepts
    them (also required on the MIMIC demo).
    ``patient_limit``: use only the first N patients (sorted by id) and
    their clinical resources — smoke runs on large corpora.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    injection, corpus_counts = _inject(
        corpus, seed=seed, num_dup_patients=num_dup_patients,
        dups_per_patient=dups_per_patient,
        clean_duplicate_ratio=clean_duplicate_ratio,
        stack_probability=stack_probability,
        profile_weights=profile_weights, realistic_names=realistic_names,
        rebase_dobs=rebase_dobs, patient_limit=patient_limit)

    report: dict = {
        "schema": "fhir4ds.realism/1",
        "corpus": {
            "path": str(corpus),
            "resource_counts": corpus_counts,
        },
        "seed": seed,
        "config": {
            "num_dup_patients": num_dup_patients,
            "dups_per_patient": dups_per_patient,
            "clean_duplicate_ratio": clean_duplicate_ratio,
            "stack_probability": stack_probability,
            "profile_weights": (profile_weights
                                if profile_weights is not None
                                else "default"),
            "realistic_names": realistic_names,
            "rebase_dobs": rebase_dobs,
            "patient_limit": patient_limit,
        },
        "injection": {
            "gold_pairs": len(injection.gold_pairs),
            "honest_negative_patients": len(injection.honest_negative_ids),
            "names_replaced": len(injection.names_replaced),
            "birthdates_rebased": injection.birthdates_rebased,
            "gold_pair_details": [p.to_dict()
                                  for p in injection.gold_pairs],
        },
        "matching": _matching_section(injection),
        "dedup": _dedup_section(injection, output_dir),
    }
    if run_piqi:
        report["piqi"] = _piqi_section(injection)

    path = Path(report_path) if report_path else output_dir / REPORT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    # report_path lives only on the RETURNED dict, never in the file, so
    # identical runs into different directories stay byte-identical.
    report["report_path"] = str(path)
    return report


def summarize(report: dict) -> str:
    m = report["matching"]
    d = report["dedup"]
    lines = [
        f"realism benchmark — corpus {report['corpus']['path']} "
        f"(seed {report['seed']})",
        f"  gold pairs: {report['injection']['gold_pairs']}   "
        f"honest negatives: "
        f"{report['injection']['honest_negative_patients']}",
    ]
    if report["injection"].get("names_replaced"):
        lines.append(
            f"  realistic names generated for "
            f"{report['injection']['names_replaced']} patients; "
            f"{report['injection'].get('birthdates_rebased', 0)} DOBs "
            f"rebased")
    lines += [
        f"  matching: P={m['precision']} R={m['recall']} "
        f"(TP {m['true_positives']} / FP {m['false_positives']} / "
        f"FN {m['false_negatives']}; ambiguous "
        f"{m['outcomes']['ambiguous']})",
        "  per-profile recall: "
        + (", ".join(f"{k}={v}"
                     for k, v in m["per_profile_recall"].items())
           or "n/a"),
        f"  dedup: clusters={d.get('clusters', 'n/a')} "
        f"cross-patient-clusters={d.get('cross_patient_clusters', 'n/a')} "
        f"queue={d.get('curation_queue_by_kind') or '{}'}"
        + ("  [FAILED: " + d.get("error_type", "error") + "]"
           if d.get("failed") else ""),
    ]
    if d.get("failed"):
        lines.append("  dedup failure: " + d.get("error", "")[:160])
    if "piqi" in report:
        p = report["piqi"]
        lines.append(
            f"  piqi: available={p.get('available')} "
            + (f"index={p['scorecard'].get('index')}"
               if p.get("available") else
               f"error={p.get('error', '')[:80]}"))
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m fhir4ds.realism.benchmark",
        description="Realism validation benchmark: duplicate injection -> "
                    "matching P/R (+ per-profile recall) -> dedup cluster/"
                    "curation report -> optional PIQI rubric.")
    parser.add_argument("--corpus", required=True,
                        help="corpus path: MIMIC-layout NDJSON directory, "
                             "Bundle directory, or single file")
    parser.add_argument("--output-dir", required=True,
                        help="directory for the JSON report + curation queue")
    parser.add_argument("--seed", type=int, default=20261120)
    parser.add_argument("--num-dup-patients", type=int, default=10,
                        help="patients receiving duplicates "
                             "(-1 = every patient)")
    parser.add_argument("--dups-per-patient", type=int, default=1)
    parser.add_argument("--clean-duplicate-ratio", type=float, default=0.2)
    parser.add_argument("--stack-probability", type=float, default=0.3)
    parser.add_argument("--profile-weights", default=None,
                        help='JSON dict, e.g. \'{"name_transliteration": 1}\'')
    parser.add_argument("--realistic-names", action="store_true",
                        help="replace synthetic MIMIC-style names "
                             "(Patient_<id> literals) with generated "
                             "realistic names before injection")
    parser.add_argument("--rebase-dobs", action="store_true",
                        help="shift future de-identification-shifted "
                             "birthDates back by whole centuries")
    parser.add_argument("--patient-limit", type=int, default=None,
                        help="use only the first N patients (sorted) — "
                             "smoke runs on large corpora")
    parser.add_argument("--piqi", action="store_true",
                        help="also evaluate the packaged sample PIQI rubric")
    args = parser.parse_args(argv)

    weights = None
    if args.profile_weights:
        weights = json.loads(args.profile_weights)

    num_dup = None if args.num_dup_patients < 0 else args.num_dup_patients
    report = run_benchmark(
        args.corpus, output_dir=args.output_dir, seed=args.seed,
        num_dup_patients=num_dup, dups_per_patient=args.dups_per_patient,
        clean_duplicate_ratio=args.clean_duplicate_ratio,
        stack_probability=args.stack_probability,
        profile_weights=weights, realistic_names=args.realistic_names,
        rebase_dobs=args.rebase_dobs, patient_limit=args.patient_limit,
        run_piqi=args.piqi)
    print(summarize(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
