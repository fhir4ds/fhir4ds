#!/usr/bin/env python3
"""
Comparison benchmarking script: cql-py vs clinical-reasoning.

Run from the benchmarking/ directory:
  python3 run_comparison.py [--runs N] [--skip-cr] [--skip-cql-py]

Runs all 46 2025 QI-Core measures N times each, recording per-run
parse_ms, translation_ms, execution_ms, and accuracy_pct for both engines.

Outputs:
  output/comparison_runs/cql_py_runs.json
  output/comparison_runs/cr_runs.json
  output/comparison_runs/summary_stats.json
  COMPARISON_TESTING.md
"""
import json
import subprocess
import sys
import time
import statistics
from pathlib import Path
from typing import Any

# ── Paths ────────────────────────────────────────────────────────────────────

BENCHMARKS_DIR = Path(__file__).parent
PROJECT_ROOT = BENCHMARKS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BENCHMARKS_DIR))

from fhir4ds.dqm.tests.conformance.config import get_suite_paths, OUTPUT_CQL_PY_DIR
from fhir4ds.dqm.tests.conformance.cli import _discover_measures
from fhir4ds.dqm.tests.conformance.database import BenchmarkDatabase
from fhir4ds.dqm.tests.conformance.loader import load_test_suite
from fhir4ds.dqm.tests.conformance.runner import run_measure

OUTPUT_RUNS_DIR = BENCHMARKS_DIR / "output" / "comparison_runs"
OUTPUT_RUNS_DIR.mkdir(parents=True, exist_ok=True)

JAR = BENCHMARKS_DIR / "clinical-reasoning" / "build" / "libs" / "clinical-reasoning-benchmark-1.0.0-all.jar"

SUITE_PATHS = get_suite_paths("2025")
MEASURE_DIR  = SUITE_PATHS["tests_dir"]
CQL_DIR      = SUITE_PATHS["cql_dir"]
VALUESET_DIR = SUITE_PATHS["valueset_dir"]
BUNDLE_DIR   = SUITE_PATHS["bundle_dir"]

N_RUNS = 5
PERIOD_START = "2026-01-01"
PERIOD_END   = "2026-12-31"

# Known skip (hang / no data)
SKIP = {
    "BreastCancerScreeningDQMDraft",  # DQM draft, not in official suite
    "CMS1218",  # infinite loop (50+ min at 99% CPU)
    "CMS139",   # not present in submodule
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _pct(a: int, b: int) -> float:
    return round(100.0 * a / b, 2) if b else 0.0


# ── cql-py benchmark ─────────────────────────────────────────────────────────

def _collect_vs_paths(configs):
    """Collect unique valueset paths across all configs."""
    seen, paths = set(), []
    for c in configs:
        for p in c.valueset_paths:
            key = str(p)
            if key not in seen:
                seen.add(key)
                paths.append(p)
    return paths


def run_cql_py_all(n_runs: int) -> list[dict]:
    """Run all measures n_runs times with cql-py. Returns list of run records."""
    import gc
    configs = [c for c in _discover_measures("2025") if c.id not in SKIP]
    print(f"\n[cql-py] {len(configs)} measures × {n_runs} runs")

    all_records: list[dict] = []

    for run_idx in range(1, n_runs + 1):
        print(f"\n  Run {run_idx}/{n_runs}")
        db = BenchmarkDatabase()

        # Load test data and valuesets (mirrors cli.py setup)
        db.load_all_test_data(configs)
        db.load_all_valuesets(_collect_vs_paths(configs))

        for i, config in enumerate(configs, 1):
            print(f"    [{i:2d}/{len(configs)}] {config.id}", end="", flush=True)
            try:
                # Scope resources to this measure (prevents cross-contamination)
                if len(configs) > 1:
                    db.scope_to_measure(config.id)

                # Clear CQL variable state from previous measure
                try:
                    from fhir4ds.cql.duckdb.udf.variable import clear_variables
                    clear_variables(db.conn)
                except ImportError:
                    pass

                gc.collect()

                suite = load_test_suite(config)
                result = run_measure(
                    conn=db.conn,
                    measure_config=config,
                    test_suite=suite,
                    verbose=False,
                    all_columns=False,
                    audit=False,
                )
                parse_ms        = result.timings.get("cql_parse_ms", 0.0)
                translation_ms  = result.timings.get("sql_generation_ms", 0.0)
                execution_ms    = result.timings.get("sql_execution_ms", 0.0)
                patient_count   = result.patient_count

                # Accuracy
                if result.comparison:
                    matching  = result.comparison.matching_patients
                    total_pts = result.comparison.total_patients
                    accuracy  = _pct(matching, total_pts)
                else:
                    matching  = 0
                    total_pts = patient_count
                    accuracy  = 0.0

                record = {
                    "run": run_idx,
                    "measure_id": config.id,
                    "patient_count": patient_count,
                    "parse_ms": round(parse_ms, 3),
                    "translation_ms": round(translation_ms, 3),
                    "execution_ms": round(execution_ms, 3),
                    "matching_patients": matching,
                    "total_patients": total_pts,
                    "accuracy_pct": accuracy,
                    "status": "success",
                    "error": None,
                }
                print(f"  {execution_ms:.0f}ms exec, {accuracy:.1f}% acc")
            except Exception as exc:
                record = {
                    "run": run_idx,
                    "measure_id": config.id,
                    "patient_count": 0,
                    "parse_ms": 0.0,
                    "translation_ms": 0.0,
                    "execution_ms": 0.0,
                    "matching_patients": 0,
                    "total_patients": 0,
                    "accuracy_pct": 0.0,
                    "status": "error",
                    "error": str(exc)[:200],
                }
                print(f"  ERROR: {exc!s:.80}")

            all_records.append(record)

        db.conn.close()

    return all_records


# ── clinical-reasoning benchmark ─────────────────────────────────────────────

import re as _re

def _normalize_cr_measure_id(raw_id: str) -> str:
    """Convert 'CMS0334FHIRPCCesareanBirth' → 'CMS0334'."""
    m = _re.match(r"(CMS\d+)", raw_id, _re.IGNORECASE)
    return m.group(1) if m else raw_id


def merge_cr_run_files(n_runs: int) -> list[dict]:
    """Merge pre-computed cr_run_N.json files into the standard record format.

    The Java benchmark script saves one JSON file per run. This function reads
    those files and produces a flat list of per-measure-run records compatible
    with compute_stats() / write_report().
    """
    records: list[dict] = []
    for run_idx in range(1, n_runs + 1):
        run_file = OUTPUT_RUNS_DIR / f"cr_run_{run_idx}.json"
        if not run_file.exists():
            print(f"  [CR merge] Run {run_idx} file not found: {run_file}")
            continue
        try:
            entries = json.loads(run_file.read_text())
        except Exception as exc:
            print(f"  [CR merge] Failed to parse {run_file}: {exc}")
            continue

        for entry in entries:
            raw_mid = entry.get("measure_id", "")
            mid = _normalize_cr_measure_id(raw_mid)
            if mid in SKIP:
                continue

            timings     = entry.get("timings", {})
            translation = timings.get("translation_ms", 0.0)
            execution   = timings.get("total_execution_ms", 0.0)

            patients    = entry.get("patients", [])
            total_pts   = len(patients)
            # In the CR benchmark, "success" means the evaluation ran without error,
            # not that the outcome matched the expected test result.
            success_pts = sum(1 for p in patients if p.get("status") == "success")
            accuracy    = _pct(success_pts, total_pts)

            record = {
                "run": run_idx,
                "measure_id": mid,
                "patient_count": total_pts,
                "translation_ms": round(translation, 3),
                "execution_ms": round(execution, 3),
                "matching_patients": success_pts,
                "total_patients": total_pts,
                "accuracy_pct": accuracy,
                "status": "success" if total_pts > 0 else "error",
                "error": None,
            }
            records.append(record)
        print(f"  [CR merge] Run {run_idx}: {len(entries)} measures loaded")
    return records


def run_cr_all(n_runs: int) -> list[dict]:
    """Run all measures n_runs times with clinical-reasoning (Java). Returns list of run records."""
    if not JAR.exists():
        print(f"[clinical-reasoning] JAR not found at {JAR}; skipping.")
        return []

    print(f"\n[clinical-reasoning] {n_runs} runs")
    all_records: list[dict] = []

    for run_idx in range(1, n_runs + 1):
        tmp_output = OUTPUT_RUNS_DIR / f"cr_run_{run_idx}_raw.json"
        print(f"\n  Run {run_idx}/{n_runs}")
        cmd = [
            "java", "-Xmx4g",
            "-jar", str(JAR),
            "--measure-dir", str(MEASURE_DIR),
            "--cql-dir",     str(CQL_DIR),
            "--valueset-dir",str(VALUESET_DIR),
            "--valueset-bundle-dir", str(BUNDLE_DIR),
            "--period-start", PERIOD_START,
            "--period-end",   PERIOD_END,
            "--output",       str(tmp_output),
        ]
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            elapsed = time.perf_counter() - t0
            if proc.returncode != 0:
                print(f"  Java exited {proc.returncode}: {proc.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print("  Java run timed out (30min)")
            continue
        except Exception as exc:
            print(f"  Java failed: {exc}")
            continue

        # Parse output
        if not tmp_output.exists():
            print("  No output file produced.")
            continue

        try:
            raw = json.loads(tmp_output.read_text())
        except Exception as exc:
            print(f"  Failed to parse output: {exc}")
            continue

        for entry in raw:
            mid = entry.get("measure_id", "")
            if mid in SKIP:
                continue
            timings       = entry.get("timings", {})
            translation   = timings.get("translation_ms", 0.0)
            execution     = timings.get("execution_ms", 0.0)
            patients      = entry.get("patient_results", [])
            total_pts     = len(patients)
            matching      = sum(1 for p in patients if p.get("matches_expected", False))
            accuracy      = _pct(matching, total_pts)

            record = {
                "run": run_idx,
                "measure_id": mid,
                "patient_count": total_pts,
                "translation_ms": round(translation, 3),
                "execution_ms": round(execution, 3),
                "matching_patients": matching,
                "total_patients": total_pts,
                "accuracy_pct": accuracy,
                "status": "success" if entry.get("status") == "success" else "error",
                "error": entry.get("error"),
            }
            all_records.append(record)
            print(f"    {mid}: {execution:.0f}ms exec, {accuracy:.1f}% acc")

    return all_records


# ── Statistics ───────────────────────────────────────────────────────────────

def per_patient_exec_ms(records: list[dict]) -> list[float]:
    """Per-patient execution times for successful runs with >0 patients."""
    return [
        r["execution_ms"] / r["patient_count"]
        for r in records
        if r["status"] == "success" and r["patient_count"] > 0
        and r["execution_ms"] > 0
    ]


def stat_summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "p25": round(sorted(values)[len(values) // 4], 3),
        "p75": round(sorted(values)[3 * len(values) // 4], 3),
    }


def measures_at_100pct(records: list[dict]) -> set[str]:
    """Return set of measure IDs where ALL runs had 100% accuracy."""
    from collections import defaultdict
    acc_by_measure: dict[str, list[float]] = defaultdict(list)
    for r in records:
        if r["status"] == "success":
            acc_by_measure[r["measure_id"]].append(r["accuracy_pct"])
    return {mid for mid, accs in acc_by_measure.items() if all(a == 100.0 for a in accs)}


def compute_stats(cql_py_records: list[dict], cr_records: list[dict]) -> dict:
    """Compute the required statistics."""

    cql_100 = measures_at_100pct(cql_py_records)
    cr_100  = measures_at_100pct(cr_records) if cr_records else set()
    both_100 = cql_100 & cr_100

    # Per-patient exec ms for cql-py
    cql_all_pp    = per_patient_exec_ms(cql_py_records)
    cql_100_pp    = per_patient_exec_ms([r for r in cql_py_records if r["measure_id"] in cql_100])
    cql_both_pp   = per_patient_exec_ms([r for r in cql_py_records if r["measure_id"] in both_100])

    # Per-patient exec ms for clinical-reasoning
    cr_all_pp     = per_patient_exec_ms(cr_records) if cr_records else []
    cr_100_pp     = per_patient_exec_ms([r for r in cr_records if r["measure_id"] in cr_100]) if cr_records else []
    cr_both_pp    = per_patient_exec_ms([r for r in cr_records if r["measure_id"] in both_100]) if cr_records else []

    return {
        "cql_py_100pct_measures": sorted(cql_100),
        "cr_100pct_measures":     sorted(cr_100),
        "both_100pct_measures":   sorted(both_100),
        "cql_py": {
            "all_runs_all_measures":      stat_summary(cql_all_pp),
            "all_runs_cql100_measures":   stat_summary(cql_100_pp),
            "all_runs_both100_measures":  stat_summary(cql_both_pp),
        },
        "clinical_reasoning": {
            "all_runs_all_measures":      stat_summary(cr_all_pp),
            "all_runs_cr100_measures":    stat_summary(cr_100_pp),
            "all_runs_both100_measures":  stat_summary(cr_both_pp),
        },
    }


# ── Report writer ─────────────────────────────────────────────────────────────

def write_report(cql_py_records: list[dict], cr_records: list[dict], stats: dict) -> Path:
    from collections import defaultdict

    out = BENCHMARKING_DIR / "COMPARISON_TESTING.md"

    def fmt(v):
        if v is None: return "—"
        return f"{v:.2f}ms"

    def measure_summary_table(records: list[dict], engine_label: str) -> str:
        # Group by measure
        by_measure: dict[str, list[dict]] = defaultdict(list)
        for r in records:
            if r["status"] == "success":
                by_measure[r["measure_id"]].append(r)

        lines = []
        lines.append(f"### {engine_label} — Per-Measure Summary (all runs)")
        lines.append("")
        lines.append("| Measure | Patients | Runs | Mean exec (ms) | Median exec (ms) | Min (ms) | Max (ms) | Mean exec/patient (ms) | Accuracy (all runs) |")
        lines.append("|---------|----------|------|----------------|-----------------|----------|----------|----------------------|---------------------|")

        for mid in sorted(by_measure):
            runs = by_measure[mid]
            execs = [r["execution_ms"] for r in runs]
            pts = runs[0]["patient_count"] if runs else 0
            if pts > 0:
                pp = [r["execution_ms"] / r["patient_count"] for r in runs]
                mean_pp = statistics.mean(pp)
            else:
                mean_pp = 0.0
            accs = [r["accuracy_pct"] for r in runs]
            acc_str = "100%" if all(a == 100.0 for a in accs) else f"{statistics.mean(accs):.1f}% avg"

            lines.append(
                f"| {mid} | {pts} | {len(runs)} "
                f"| {statistics.mean(execs):.1f} | {statistics.median(execs):.1f} "
                f"| {min(execs):.1f} | {max(execs):.1f} "
                f"| {mean_pp:.2f} | {acc_str} |"
            )
        return "\n".join(lines)

    def run_detail_table(records: list[dict], engine_label: str) -> str:
        lines = []
        lines.append(f"### {engine_label} — Run-Level Detail")
        lines.append("")
        if engine_label.startswith("cql-py"):
            lines.append("| Run | Measure | Patients | Parse (ms) | Translation (ms) | Execution (ms) | Exec/Patient (ms) | Accuracy |")
            lines.append("|-----|---------|----------|-----------|-----------------|----------------|------------------|----------|")
        else:
            lines.append("| Run | Measure | Patients | Translation (ms) | Execution (ms) | Exec/Patient (ms) | Accuracy |")
            lines.append("|-----|---------|----------|-----------------|----------------|------------------|----------|")

        for r in sorted(records, key=lambda x: (x["run"], x["measure_id"])):
            if r["status"] != "success":
                continue
            pts = r["patient_count"]
            pp  = r["execution_ms"] / pts if pts else 0.0
            acc = f"{r['accuracy_pct']:.1f}%"
            if engine_label.startswith("cql-py"):
                lines.append(
                    f"| {r['run']} | {r['measure_id']} | {pts} "
                    f"| {r['parse_ms']:.1f} | {r['translation_ms']:.1f} "
                    f"| {r['execution_ms']:.1f} | {pp:.2f} | {acc} |"
                )
            else:
                lines.append(
                    f"| {r['run']} | {r['measure_id']} | {pts} "
                    f"| {r['translation_ms']:.1f} "
                    f"| {r['execution_ms']:.1f} | {pp:.2f} | {acc} |"
                )
        return "\n".join(lines)

    def stat_block(label: str, s: dict) -> str:
        if s["count"] == 0:
            return f"**{label}**: no data\n"
        return (
            f"**{label}** (n={s['count']} measure-runs)\n"
            f"- Mean: {s['mean']:.2f} ms/patient\n"
            f"- Median: {s['median']:.2f} ms/patient\n"
            f"- Range: {s['min']:.2f} – {s['max']:.2f} ms/patient\n"
            f"- P25–P75: {s['p25']:.2f} – {s['p75']:.2f} ms/patient\n"
        )

    c = stats["cql_py"]
    cr = stats["clinical_reasoning"]
    cql_100 = stats["cql_py_100pct_measures"]
    both_100 = stats["both_100pct_measures"]

    report = f"""# COMPARISON_TESTING.md
*Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}*

## Overview

This report documents performance benchmarking of **cql-py (FHIR4DS)** and **clinical-reasoning (Java)**
across all 46 2025 QI-Core measures, each engine run **{N_RUNS} times**.

Timing metrics:
- **cql-py**: `parse_ms` (CQL parsing), `translation_ms` (CQL → SQL), `execution_ms` (SQL execution against patient data)
- **clinical-reasoning**: `translation_ms` (CQL → ELM), `execution_ms` (ELM evaluation per patient)

> **Note**: `translation_ms` for cql-py is a **one-time pre-compilation step** (cached after first run).
> For production comparisons, only `execution_ms` reflects per-run cost.
>
> **Accuracy definitions differ by engine:**
> - **cql-py** accuracy = fraction of test patients whose computed population membership matches the
>   expected result in the official QI-Core test bundle (i.e., clinical correctness).
> - **clinical-reasoning** accuracy = fraction of patients that evaluated without a runtime error
>   (i.e., execution success rate). It does **not** compare outcomes against expected test results.
>   A 100% CR accuracy measure only means no exceptions were thrown, not that results are correct.

---

## Summary Statistics: SQL Execution Time Per Patient

Execution time is divided by patient count to get per-patient cost.
Statistics are computed over all ({N_RUNS} runs × N measures) = N measure-runs.

### cql-py

{stat_block("All measures (all runs)", c["all_runs_all_measures"])}
{stat_block(f"Measures with 100% accuracy ({len(cql_100)} measures, all runs)", c["all_runs_cql100_measures"])}
{stat_block(f"Measures with 100% accuracy in BOTH engines ({len(both_100)} measures, all runs)", c["all_runs_both100_measures"])}

### clinical-reasoning (Java)

{stat_block("All measures (all runs)", cr["all_runs_all_measures"])}
{stat_block(f"Measures with 100% accuracy (CR, all runs)", cr["all_runs_cr100_measures"])}
{stat_block(f"Measures with 100% accuracy in BOTH engines ({len(both_100)} measures)", cr["all_runs_both100_measures"])}

"""
    # Add speedup comparison if we have both engines' data for shared measures
    cql_both = c["all_runs_both100_measures"]
    cr_both  = cr["all_runs_both100_measures"]
    if cql_both["count"] > 0 and cr_both["count"] > 0 and cql_both["median"]:
        speedup_mean   = round(cr_both["mean"]   / cql_both["mean"],   1) if cql_both["mean"] else 0
        speedup_median = round(cr_both["median"] / cql_both["median"], 1) if cql_both["median"] else 0
        report += f"""### Speedup (cql-py vs clinical-reasoning) — {len(both_100)} shared measures

> Speedup = clinical-reasoning time ÷ cql-py time (higher = cql-py is faster)

| Metric | cql-py | clinical-reasoning | Speedup |
|--------|--------|-------------------|---------|
| Mean exec/patient | {cql_both['mean']:.2f} ms | {cr_both['mean']:.2f} ms | **{speedup_mean}×** |
| Median exec/patient | {cql_both['median']:.2f} ms | {cr_both['median']:.2f} ms | **{speedup_median}×** |

---

"""
    cr_100_list = stats["cr_100pct_measures"]
    report += f"""
## Accuracy Summary

- **cql-py 100% accuracy measures** ({len(cql_100)}): `{", ".join(cql_100) or "none"}`
- **clinical-reasoning 100% accuracy measures** ({len(cr_100_list)}): `{", ".join(cr_100_list) or "none (CR not run)"}`
- **Both engines 100%** ({len(both_100)}): `{", ".join(both_100) or "none"}`

---

## cql-py Results

{measure_summary_table(cql_py_records, "cql-py")}

---

{run_detail_table(cql_py_records, "cql-py")}

---

## clinical-reasoning Results

"""
    if cr_records:
        report += measure_summary_table(cr_records, "clinical-reasoning (Java)") + "\n\n---\n\n"
        report += run_detail_table(cr_records, "clinical-reasoning (Java)") + "\n"
    else:
        report += "_clinical-reasoning JAR not available or produced no results._\n"

    out.write_text(report)
    print(f"\n[Report] Written to {out}")
    return out


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Run cql-py and clinical-reasoning 5× each")
    ap.add_argument("--runs", type=int, default=N_RUNS)
    ap.add_argument("--skip-cr", action="store_true", help="Skip clinical-reasoning runs")
    ap.add_argument("--skip-cql-py", action="store_true", help="Skip cql-py runs (use cached)")
    args = ap.parse_args()

    cql_py_cache = OUTPUT_RUNS_DIR / "cql_py_runs.json"
    cr_cache     = OUTPUT_RUNS_DIR / "cr_runs.json"

    if args.skip_cql_py and cql_py_cache.exists():
        print("[cql-py] Loading cached results...")
        cql_py_records = json.loads(cql_py_cache.read_text())
    else:
        cql_py_records = run_cql_py_all(args.runs)
        cql_py_cache.write_text(json.dumps(cql_py_records, indent=2))
        print(f"[cql-py] Saved {len(cql_py_records)} records to {cql_py_cache}")

    if args.skip_cr and cr_cache.exists():
        print("[CR] Loading cached results...")
        cr_records = json.loads(cr_cache.read_text())
    elif args.skip_cr:
        # Auto-detect pre-computed cr_run_N.json files from external benchmark run
        run_files = sorted(OUTPUT_RUNS_DIR.glob("cr_run_[0-9]*.json"))
        if run_files:
            n_found = len(run_files)
            print(f"[CR] Found {n_found} pre-computed run files; merging...")
            cr_records = merge_cr_run_files(n_found)
            cr_cache.write_text(json.dumps(cr_records, indent=2))
            print(f"[CR] Merged {len(cr_records)} records → {cr_cache}")
        else:
            print("[CR] No pre-computed run files found; skipping.")
            cr_records = []
    elif not args.skip_cr:
        cr_records = run_cr_all(args.runs)
        cr_cache.write_text(json.dumps(cr_records, indent=2))
        print(f"[CR] Saved {len(cr_records)} records to {cr_cache}")
    else:
        cr_records = []

    stats = compute_stats(cql_py_records, cr_records)
    stats_path = OUTPUT_RUNS_DIR / "summary_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2))
    print(f"[Stats] Saved to {stats_path}")

    report_path = write_report(cql_py_records, cr_records, stats)
    print(f"\n✅ Done. Report: {report_path}")
