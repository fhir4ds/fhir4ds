#!/usr/bin/env python3
"""AMUX-39 verification: streaming (S3/http chunk prefix) vs local staging.

  python3 benchmarks/scaling/run_s3_stream_check.py \
      --patients 1000 \
      [--endpoint http://localhost:7070 --access-key ... --secret-key ...]

Stages the SAME rung twice (local converted dir vs s3://chunk prefix),
then runs the drug-exposure SQLQuery workload leg against each through the
standard memory-guard harness (run_leg: launch gate, watchdogs, per-rep
meminfo). Produces results/omop/s3_stream_check_<N>.json comparing exec
time and peak RSS, proving the memory guards hold when scans stream off
object storage instead of local disk.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from omop_common import DB_DIR, RESULTS_DIR, run_leg

BENCH = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients", type=int, default=1000)
    ap.add_argument("--prefix", default="s3://fhir4ds-omop-scaling/chunks")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--access-key", default=None)
    ap.add_argument("--secret-key", default=None)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--rss-cap-mb", type=float, default=24000.0)
    args = ap.parse_args()

    n = args.patients
    out = {"patients": n, "prefix": args.prefix, "variants": {}}

    for variant in ("local", "s3"):
        db = DB_DIR / f"rung{n}_{variant}s3.duckdb"
        stage_cmd = [str(BENCH / "stage_omop_rung.py"),
                     "--patients", str(n), "--db", str(db),
                     "--staging-suffix", f"_{variant}s3"]
        leg_cmd = [str(BENCH / "omop_leg.py"), "--db", str(db),
                   "--workload", "drug_sqlquery", "--patients", str(n),
                   "--reps", str(args.reps),
                   "--rss-cap-mb", str(args.rss_cap_mb),
                   "--duckdb-memory-limit", "8GB", "--threads", "16",
                   "--out-suffix", f"_{variant}s3"]
        if variant == "s3":
            s3_args = ["--chunk-prefix", args.prefix]
            if args.endpoint:
                s3_args += ["--s3-endpoint", args.endpoint]
            if args.access_key:
                s3_args += ["--s3-access-key", args.access_key,
                            "--s3-secret-key", args.secret_key or ""]
            stage_cmd += s3_args
            # legs take the secret/endpoint args but NOT --chunk-prefix
            skip = False
            for a in s3_args:
                if skip:
                    skip = False
                    continue
                if a == "--chunk-prefix":
                    skip = True
                    continue
                leg_cmd.append(a)
        leg = run_leg(stage_cmd, rss_cap_mb=args.rss_cap_mb,
                      gate_mb=12000, label=f"stage-{variant}",
                      log_path=RESULTS_DIR / f"logs/s3check-stage-{variant}.log")
        if leg["returncode"] != 0:
            out["variants"][variant] = {"stage": leg, "status": "stage-failed"}
            continue
        leg = run_leg(leg_cmd, rss_cap_mb=args.rss_cap_mb * 2,
                      gate_mb=args.rss_cap_mb,
                      label=f"leg-{variant}",
                      log_path=RESULTS_DIR / f"logs/s3check-leg-{variant}.log")
        rec = {"status": "ok" if leg["returncode"] == 0
               else f"rc={leg['returncode']}"}
        res = RESULTS_DIR / f"rung{n}_drug_sqlquery_{variant}s3.json"
        if leg["returncode"] == 0 and res.exists():
            d = json.loads(res.read_text())
            rec["exec_ms"] = d["exec"]["exec_ms"]
            rec["exec_ms_median"] = d["exec"]["exec_ms_median"]
            rec["rows"] = d["exec"]["rows"]
            rec["peak_rss_mb"] = d["peak_rss_mb"]
            rec["host_meminfo"] = d["exec"].get("host_meminfo_per_rep")
        out["variants"][variant] = {"leg": leg, **rec}

    a = out["variants"].get("local", {})
    b = out["variants"].get("s3", {})
    if a.get("exec_ms_median") and b.get("exec_ms_median"):
        out["streaming_vs_local_exec_ratio"] = round(
            b["exec_ms_median"] / a["exec_ms_median"], 2)
    path = RESULTS_DIR / f"s3_stream_check_{n}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "variants"},
                     indent=2))
    for v in ("local", "s3"):
        r = out["variants"].get(v, {})
        print(f"{v}: {r.get('status')} exec={r.get('exec_ms')} "
              f"peak={r.get('peak_rss_mb')}MB")
    print(f"saved {path}")


if __name__ == "__main__":
    main()
