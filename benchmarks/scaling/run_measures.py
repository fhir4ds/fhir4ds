#!/usr/bin/env python3
"""Quality-measure scaling benchmark: fhir4ds (compile-to-SQL) vs extrapolated
clinical-reasoning (Java) per-patient baseline.

Runs 3 eCQMs of increasing complexity (CMS68 low, CMS125 medium, CMS2 high)
against nested Synthea cohorts (100 / 1,000 / 5,000 patients) taken as a
deterministic sorted prefix of the s3-raw bundle corpus.

One fresh process per rung. Data is loaded once per rung into an in-memory
DuckDB database via FHIRDataLoader; each measure is then parsed, translated
and executed REPEATS times. Phase wall-times and peak RSS are recorded.

Usage:
  python3 benchmarks/scaling/run_measures.py --rung 100
  python3 benchmarks/scaling/run_measures.py --rung 5000 --repeats 1
"""
from __future__ import annotations

import argparse
import gc
import glob
import json
import os
import resource
import sys
import threading
import time
from pathlib import Path

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BENCHMARKS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_ROOT = Path("/mnt/d/scaling-data/s3-raw/output/fhir")
RESULTS_DIR = BENCHMARKS_DIR / "scaling" / "results"
MEASURES = ["CMS68", "CMS125", "CMS2"]
MP_START = "2026-01-01"
MP_END = "2026-12-31"
LOAD_CHUNK_BUNDLES = 50


def rss_mb() -> float:
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    return -1.0


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def start_rss_watchdog(abort_mb: float) -> None:
    """Abort the process if RSS climbs past abort_mb (memory-cap discipline)."""

    def _loop() -> None:
        while True:
            rss = rss_mb()
            if rss > abort_mb:
                print(
                    f"ABORT: RSS {rss:,.0f}MB exceeded cap {abort_mb:,.0f}MB",
                    flush=True,
                )
                os._exit(3)
            time.sleep(2)

    t = threading.Thread(target=_loop, name="rss-watchdog", daemon=True)
    t.start()


def _render_profile_tree(node: dict, depth: int = 0) -> list[str]:
    lines = []
    name = node.get("operator_name") or "<root>"
    timing = node.get("operator_timing")
    rows = node.get("operator_cardinality")
    timing_s = f"{timing * 1000:,.1f}ms" if isinstance(timing, (int, float)) else "?"
    lines.append(f"{'  ' * depth}{name}  [{timing_s}] rows={rows}")
    for child in node.get("children", []) or []:
        lines.extend(_render_profile_tree(child, depth + 1))
    return lines


def capture_profile(con, sql: str, mid: str, tag: str) -> dict:
    """Run EXPLAIN ANALYZE once (re-executes the query) and persist the JSON
    operator profile plus a rendered tree. One execution, both artifacts."""
    prof_dir = RESULTS_DIR / "profiles"
    prof_dir.mkdir(parents=True, exist_ok=True)
    json_path = prof_dir / f"{tag}_{mid}_profile.json"
    txt_path = prof_dir / f"{tag}_{mid}_explain_analyze.txt"
    con.execute("SET enable_profiling='json'")
    try:
        t0 = time.perf_counter()
        rows = con.execute("EXPLAIN ANALYZE " + sql).fetchall()
        analyze_ms = (time.perf_counter() - t0) * 1000
    finally:
        con.execute("RESET enable_profiling")
    payload = json.loads(rows[0][1])
    json_path.write_text(json.dumps(payload, indent=1))
    txt_path.write_text("\n".join(_render_profile_tree(payload)) + "\n")
    return {
        "explain_analyze_ms": round(analyze_ms, 1),
        "latency_ms": round((payload.get("latency") or 0) * 1000, 1),
        "profile_json": str(json_path),
        "explain_analyze_txt": str(txt_path),
        "peak_buffer_mb": round((payload.get("system_peak_buffer_memory") or 0) / 2**20, 1),
        "peak_temp_dir_mb": round((payload.get("system_peak_temp_dir_size") or 0) / 2**20, 1),
        "rows_scanned": payload.get("cumulative_rows_scanned"),
    }


def collect_bundle_files(n_patients: int, data_root: Path) -> tuple[list[str], int]:
    """Deterministic nested prefix: the two *information* files plus the
    first n_patients patient bundles in sorted order."""
    files = sorted(glob.glob(str(data_root / "*.json")))
    info, patients = [], []
    for f in files:
        base = os.path.basename(f).lower()
        if "information" in base:
            info.append(f)
        else:
            patients.append(f)
    selected = info + patients[:n_patients]
    return selected, len(patients)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rung", type=int, required=True, help="number of patients")
    ap.add_argument("--measures", default=",".join(MEASURES))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--data-root", default=str(DATA_ROOT))
    ap.add_argument("--tag", default=None, help="result filename tag")
    ap.add_argument("--memory-limit", default="32GB", help="DuckDB memory_limit")
    ap.add_argument(
        "--rss-abort-mb",
        type=float,
        default=50000.0,
        help="hard RSS cap; the process exits if exceeded (default 50000 = 50GB)",
    )
    ap.add_argument(
        "--profile",
        action="store_true",
        help="after timed reps, capture EXPLAIN ANALYZE + JSON profile per measure",
    )
    args = ap.parse_args()

    data_root = Path(args.data_root)
    start_rss_watchdog(args.rss_abort_mb)
    print(
        f"config: memory_limit={args.memory_limit} rss_abort={args.rss_abort_mb:,.0f}MB "
        f"profile={args.profile}",
        flush=True,
    )

    from fhir4ds.dqm.tests.conformance.cli import _discover_measures
    from fhir4ds.dqm.tests.conformance.database import BenchmarkDatabase

    measure_ids = [m.strip() for m in args.measures.split(",") if m.strip()]
    configs = {c.id: c for c in _discover_measures("2025")}

    db = BenchmarkDatabase()
    db.conn.execute("SET threads=32")
    db.conn.execute(f"SET memory_limit='{args.memory_limit}'")
    db.conn.execute("SET scalar_subquery_error_on_multiple_rows=false")
    tmp_dir = "/tmp/opencode/duckdb_tmp"
    os.makedirs(tmp_dir, exist_ok=True)
    db.conn.execute(f"SET temp_directory='{tmp_dir}'")
    print(f"setup ok; measures={measure_ids}", flush=True)

    # Valuesets for the selected measures
    vs_paths = []
    seen = set()
    for mid in measure_ids:
        for p in configs[mid].valueset_paths:
            if str(p) not in seen:
                seen.add(str(p))
                vs_paths.append(p)
    t0 = time.perf_counter()
    db.load_all_valuesets(vs_paths)
    vs_s = time.perf_counter() - t0

    # Cohort data — chunked bundle loading
    files, total_available = collect_bundle_files(args.rung, data_root)
    from fhir4ds.cql import FHIRDataLoader

    loader = FHIRDataLoader(db.conn)
    t0 = time.perf_counter()
    n_res = 0
    for i in range(0, len(files), LOAD_CHUNK_BUNDLES):
        chunk_files = files[i : i + LOAD_CHUNK_BUNDLES]
        resources = []
        for f in chunk_files:
            bundle = json.load(open(f, encoding="utf-8"))
            if bundle.get("resourceType") != "Bundle":
                continue
            for entry in bundle.get("entry", []):
                r = entry.get("resource")
                if isinstance(r, dict) and r.get("resourceType"):
                    resources.append(r)
        n_res += loader.load_resources(resources)
        del resources
        if (i // LOAD_CHUNK_BUNDLES) % 10 == 0:
            print(
                f"  loaded {n_res:,} resources "
                f"({i + len(chunk_files)}/{len(files)} bundles) "
                f"rss={rss_mb():,.0f}MB",
                flush=True,
            )
    load_s = time.perf_counter() - t0
    print(f"data load done: {n_res:,} resources in {load_s:.1f}s", flush=True)
    n_pat = db.conn.execute(
        "SELECT count(DISTINCT patient_ref) FROM resources WHERE resourceType='Patient'"
    ).fetchone()[0]
    type_counts = dict(
        db.conn.execute(
            "SELECT resourceType, count(*) FROM resources GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    )

    record = {
        "rung": args.rung,
        "requested_patients": args.rung,
        "actual_patients": n_pat,
        "resources_loaded": n_res,
        "type_counts": type_counts,
        "valueset_load_s": round(vs_s, 3),
        "data_load_s": round(load_s, 3),
        "rss_after_load_mb": round(rss_mb(), 1),
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "duckdb_memory_limit": args.memory_limit,
        "rss_abort_mb": args.rss_abort_mb,
        "mp": [MP_START, MP_END],
        "measures": {},
    }

    # Translate + execute each measure
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator import CQLToSQLTranslator

    for mid in measure_ids:
        cfg = configs[mid]
        print(f"--- {mid} start rss={rss_mb():,.0f}MB ---", flush=True)
        try:
            gc.collect()
            try:
                from fhir4ds.cql.duckdb.udf.variable import clear_variables
                clear_variables(db.conn)
            except ImportError:
                pass

            t0 = time.perf_counter()
            library = parse_cql(cfg.cql_path.read_text())
            parse_ms = (time.perf_counter() - t0) * 1000

            def library_loader(alias, version=None, _cfg=cfg):
                for path in _cfg.include_paths:
                    lib_file = path / f"{alias}.cql"
                    if lib_file.exists():
                        return parse_cql(lib_file.read_text())
                return None

            translator = CQLToSQLTranslator(
                connection=db.conn,
                library_loader=library_loader,
            )
            t0 = time.perf_counter()
            translator.translate_library(library)
            lib_ms = (time.perf_counter() - t0) * 1000

            pop_defs, _ = __import__(
                "fhir4ds.dqm.tests.conformance.runner", fromlist=["x"]
            )._normalize_population_definitions(
                cfg.population_definitions,
                {s.name for s in library.statements
                 if type(s).__name__ == "Definition"},
            )
            t0 = time.perf_counter()
            sql = translator.translate_library_to_population_sql(
                library=library,
                output_columns={d: d for d in pop_defs},
                parameters={"Measurement Period": (MP_START, MP_END)},
                patient_ids=None,
            )
            gen_ms = (time.perf_counter() - t0) * 1000

            exec_ms_list, pop_counts, rows = [], None, 0
            for rep in range(args.repeats):
                t0 = time.perf_counter()
                df = db.conn.execute(sql).df()
                exec_ms_list.append(round((time.perf_counter() - t0) * 1000, 1))
                rows = len(df)
                print(f"  [{mid}] rep{rep + 1} done rss={rss_mb():,.0f}MB "
                      f"peak={peak_rss_mb():,.0f}MB", flush=True)

                def _truthy(v) -> bool:
                    if v is None:
                        return False
                    if isinstance(v, (list, tuple, set)):
                        return len(v) > 0
                    if isinstance(v, float):
                        return v == v and v != 0.0  # NaN-safe
                    if hasattr(v, "size"):  # numpy array
                        return v.size > 0
                    return bool(v)

                pop_counts = {
                    c: sum(1 for v in df[c] if _truthy(v))
                    for c in df.columns if c != "patient_id"
                }

            # Persist the generated SQL for offline structural analysis
            sql_dir = RESULTS_DIR / "sql"
            sql_dir.mkdir(parents=True, exist_ok=True)
            (sql_dir / f"{mid}.sql").write_text(sql)

            profile_info = None
            if args.profile:
                gc.collect()
                print(f"  [{mid}] profiling (EXPLAIN ANALYZE, re-executes)...",
                      flush=True)
                profile_info = capture_profile(
                    db.conn, sql, mid, args.tag or f"rung{args.rung}"
                )
                print(f"  [{mid}] profile done in "
                      f"{profile_info['explain_analyze_ms']:,.0f}ms "
                      f"rss={rss_mb():,.0f}MB", flush=True)

            mrec = {
                "status": "success",
                "patients": rows,
                "parse_ms": round(parse_ms, 1),
                "library_translation_ms": round(lib_ms, 1),
                "sql_generation_ms": round(gen_ms, 1),
                "sql_chars": len(sql),
                "exec_ms": exec_ms_list,
                "exec_ms_median": sorted(exec_ms_list)[len(exec_ms_list) // 2],
                "populations": pop_counts,
                "profile": profile_info,
                "rss_after_mb": round(rss_mb(), 1),
                "peak_rss_mb": round(peak_rss_mb(), 1),
            }
            print(f"[{mid}] rows={rows} exec_ms={exec_ms_list} pops={pop_counts}",
                  flush=True)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            mrec = {"status": "error", "error": str(exc)[:500]}
            print(f"[{mid}] ERROR: {exc}")
        record["measures"][mid] = mrec
        # Incremental save so a crash preserves completed measures
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        tag = args.tag or f"rung{args.rung}"
        (RESULTS_DIR / f"{tag}.json").write_text(json.dumps(record, indent=2))

    record["peak_rss_mb"] = round(peak_rss_mb(), 1)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tag = args.tag or f"rung{args.rung}"
    out = RESULTS_DIR / f"{tag}.json"
    out.write_text(json.dumps(record, indent=2))
    print(f"\nSaved {out}")
    print(f"peak_rss_mb={record['peak_rss_mb']} actual_patients={n_pat}")


if __name__ == "__main__":
    main()
