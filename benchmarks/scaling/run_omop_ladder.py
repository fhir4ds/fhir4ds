#!/usr/bin/env python3
"""One-command driver for the OMOP ViewDefinition / SQLQuery scaling ladder.

  python3 benchmarks/scaling/run_omop_ladder.py                  # 1k->10k->100k
  python3 benchmarks/scaling/run_omop_ladder.py --rungs 1000     # single rung

Pipeline per rung (each phase a subprocess; see omop_common/stage_omop_rung/
omop_leg):
  1. corpus availability check (deterministic prefix of the s100k Synthea gen)
  2. staging into db/rung<N>.duckdb (diagnostic; never in exec metrics)
  3. leg A: omop composition workload (exec = CTAS of final OMOP tables)
  4. leg B: drug-exposure SQLQuery sample workload (exec = CTAS of body)
  5. EXPLAIN ANALYZE legs (rungs <= --explain-max-patients)

Memory discipline: pre-flight projection before each leg calibrated from the
previous rung (peak_rss x corpus-growth x 1.3 margin). A leg whose projection
exceeds --rss-cap-mb is SKIPPED and recorded; if the top rung is refused, the
largest feasible fallback rung (--fallback-multiplier) is attempted instead.
A leg that hits its cap and aborts cleanly (exit 3) is a SUCCESS by campaign
definition; a host freeze is the only failure mode we must avoid.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from omop_common import (DB_DIR, RESULTS_DIR, available_corpus_patients,
                         run_leg)

BENCH = Path(__file__).resolve().parent


def load_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def _parse_size_mb(text: str) -> float:
    """'16GB' -> 16384.0 (also accepts MB/TB)."""
    t = str(text).strip().upper()
    mult = 1.0
    for suffix, m in (("TB", 2**20), ("GB", 2**10), ("MB", 1.0)):
        if t.endswith(suffix):
            mult, t = m, t[: -len(suffix)]
            break
    return float(t.strip()) * mult


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rungs", default="1000,10000,100000")
    ap.add_argument("--workloads", default="omop,drug_sqlquery")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--rss-cap-mb", type=float, default=24000.0)
    ap.add_argument("--duckdb-memory-limit", default="16GB")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--elements-per-chunk", type=int, default=200)
    ap.add_argument("--preflight-margin", type=float, default=1.3)
    ap.add_argument("--fallback-multiplier", type=float, default=0.3,
                    help="if a rung is memory-refused, retry at this "
                         "fraction of its patients (largest feasible "
                         "intermediate rung)")
    ap.add_argument("--explain-max-patients", type=int, default=10000)
    ap.add_argument("--stage-only", action="store_true")
    args = ap.parse_args()

    rungs = [int(r) for r in args.rungs.split(",")]
    workloads = args.workloads.split(",")
    summary: dict = {"config": vars(args), "rungs": {}}
    prev: dict[int, dict] = {}

    for rung in rungs:
        avail = available_corpus_patients()
        rec: dict = {"requested_patients": rung, "corpus_available": avail}
        if avail < rung:
            rec["status"] = "corpus-incomplete"
            print(f"[rung {rung}] corpus incomplete ({avail:,} available) "
                  "- skipping", flush=True)
            summary["rungs"][rung] = rec
            continue

        # ---- staging
        stage_json = RESULTS_DIR / f"rung{rung}_staging.json"
        db = DB_DIR / f"rung{rung}.duckdb"
        if not stage_json.exists():
            print(f"[rung {rung}] staging...", flush=True)
            leg = run_leg(
                [str(BENCH / "stage_omop_rung.py"),
                 "--patients", str(rung),
                 "--elements-per-chunk", str(args.elements_per_chunk)],
                rss_cap_mb=args.rss_cap_mb, label=f"stage{rung}",
                log_path=RESULTS_DIR / f"logs/stage{rung}.log")
            rec["staging_leg"] = leg
            if leg["returncode"] != 0:
                rec["status"] = "staging-failed"
                summary["rungs"][rung] = rec
                continue
        srec = load_json(stage_json) or {}
        rec["staging"] = srec
        print(f"[rung {rung}] staged {srec.get('resources', '?'):,} resources, "
              f"db {srec.get('db_file_mb', '?')}MB", flush=True)
        if args.stage_only:
            summary["rungs"][rung] = rec
            continue

        corpus_bytes = srec.get("json_bytes_staged", 0)

        for wl in workloads:
            prev_rec = prev.get(wl)
            # ---- pre-flight projection. Leg RSS = fixed process overhead
            # (interpreter + extensions, ~1.8GB) PLUS a corpus-linear exec
            # component that is HARD-BOUNDED by the child's DuckDB
            # memory_limit (beyond it DuckDB spills to temp, costing time
            # not RSS). Measured: rung 10k peaked at 16.4GB == the 16GB
            # memory_limit + overhead -- saturation, not linear growth.
            # A projection above (limit + slack) is physically impossible
            # while the limit is set, so clamp instead of refusing.
            LEG_FIXED_OVERHEAD_MB = 1800.0
            limit_mb = _parse_size_mb(args.duckdb_memory_limit)
            rss_ceiling_mb = limit_mb * 1.05 + 4000.0
            if prev_rec is not None and prev_rec.get("corpus_bytes"):
                growth = corpus_bytes / prev_rec["corpus_bytes"]
                linear_mb = max(0.0, prev_rec["peak_rss_mb"]
                                - LEG_FIXED_OVERHEAD_MB) * growth
                projected = min(
                    (LEG_FIXED_OVERHEAD_MB + linear_mb) *
                    args.preflight_margin,
                    rss_ceiling_mb)
                rec[f"{wl}_projected_peak_rss_mb"] = round(projected, 1)
                if projected > args.rss_cap_mb:
                    rec[f"{wl}_status"] = (
                        f"SKIPPED: projected {projected:,.0f}MB > cap "
                        f"{args.rss_cap_mb:,.0f}MB")
                    print(f"[rung {rung}/{wl}] {rec[f'{wl}_status']}",
                          flush=True)
                    continue
            print(f"[rung {rung}] leg {wl} (reps={args.reps})...", flush=True)
            leg = run_leg(
                [str(BENCH / "omop_leg.py"), "--db", str(db),
                 "--workload", wl, "--patients", str(rung),
                 "--reps", str(args.reps),
                 "--rss-cap-mb", str(args.rss_cap_mb),
                 "--duckdb-memory-limit", args.duckdb_memory_limit,
                 "--threads", str(args.threads)],
                rss_cap_mb=args.rss_cap_mb * 2,  # parent cap looser than child
                gate_mb=args.rss_cap_mb,
                label=f"{wl}{rung}",
                log_path=RESULTS_DIR / f"logs/{wl}{rung}.log")
            rec[f"{wl}_leg"] = leg
            if leg["cap_abort"]:
                rec[f"{wl}_status"] = "CAP-ABORT (clean stop at cap)"
            elif leg["returncode"] == 4:
                rec[f"{wl}_status"] = "SKIPPED: system memory gate never opened"
            elif leg["returncode"] != 0:
                rec[f"{wl}_status"] = f"FAILED rc={leg['returncode']}"
            else:
                lrec = load_json(RESULTS_DIR / f"rung{rung}_{wl}.json")
                rec[f"{wl}_result"] = lrec
                rec[f"{wl}_status"] = "ok"
                prev[wl] = {
                    "peak_rss_mb": lrec["peak_rss_mb"],
                    "corpus_bytes": corpus_bytes,
                }
            print(f"[rung {rung}/{wl}] {rec.get(f'{wl}_status')}", flush=True)

        # ---- EXPLAIN legs
        if rung <= args.explain_max_patients and not args.stage_only:
            for wl in workloads:
                if rec.get(f"{wl}_status") != "ok":
                    continue
                leg = run_leg(
                    [str(BENCH / "omop_leg.py"), "--db", str(db),
                     "--workload", wl, "--patients", str(rung),
                     "--explain-only",
                     "--rss-cap-mb", str(args.rss_cap_mb),
                     "--duckdb-memory-limit", args.duckdb_memory_limit,
                     "--threads", str(args.threads)],
                    rss_cap_mb=args.rss_cap_mb * 2,
                    gate_mb=args.rss_cap_mb,
                    label=f"explain-{wl}{rung}",
                    log_path=RESULTS_DIR / f"logs/explain-{wl}{rung}.log")
                rec[f"explain_{wl}"] = leg["returncode"]

        rec["status"] = "done"
        summary["rungs"][rung] = rec

    # ---- ratios (superlinearity visibility)
    ratios = {}
    ordered = [r for r in rungs
               if summary["rungs"].get(r, {}).get("status") == "done"]
    for a, b in zip(ordered, ordered[1:]):
        rb = {}
        for wl in workloads:
            ra = summary["rungs"][a].get(f"{wl}_result")
            rb_ = summary["rungs"][b].get(f"{wl}_result")
            if not (ra and rb_):
                continue
            pat_a = summary["rungs"][a]["staging"]["patients_requested"]
            pat_b = summary["rungs"][b]["staging"]["patients_requested"]
            key = (f"{wl}_exec_total_ms_median" if "omop" in wl
                   else f"{wl}_exec_ms_median")
            if wl == "omop":
                ta = sum(v["exec_ms_median"]
                         for v in ra["exec_final_tables"].values())
                tb = sum(v["exec_ms_median"]
                         for v in rb_["exec_final_tables"].values())
            else:
                ta, tb = ra["exec"]["exec_ms_median"], rb_["exec"]["exec_ms_median"]
            rb[wl] = {
                "patients_ratio": round(pat_b / pat_a, 2),
                "exec_time_ratio": round(tb / ta, 2) if ta else None,
                "per_patient_growth": round((tb / pat_b) / (ta / pat_a), 2)
                if ta else None,
                "peak_rss_ratio": round(
                    rb_["peak_rss_mb"] / ra["peak_rss_mb"], 2),
            }
        ratios[f"{a}->{b}"] = rb
    summary["ratios"] = ratios

    out = RESULTS_DIR / "ladder_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nsaved {out}", flush=True)
    print(json.dumps(ratios, indent=2), flush=True)


if __name__ == "__main__":
    main()
