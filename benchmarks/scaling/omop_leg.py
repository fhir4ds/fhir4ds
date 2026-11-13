#!/usr/bin/env python3
"""One measured leg (fresh process, self-guarded) for the OMOP scaling ladder.

Workloads:
  omop          Full OMOP v5.5 composition: create the omop.* view schema via
                the manifest (plan-time, diagnostics), then EXEC = CTAS of each
                of the 9 final SQLQuery tables (median of --reps), plus one
                CTAS per source ViewDefinition (the pure-ViewDefinition view
                of the same data).
  drug_sqlquery The omop-drug-exposure-sqlquery sample: 5 drug-exposure source
                views + conceptmap view materialized, sample SQLQuery Library
                parsed through the spec SQLQuery machinery (diagnostic), EXEC =
                CTAS of the sample query body (median of --reps).

Exec discipline (Joel's 2026-10-29 ruling): EXEC-ONLY is the headline. All
parse/generate/CREATE-VIEW (plan) work is timed separately as compile
diagnostics and never folded into exec figures.

Self-guard: RSS watchdog (os._exit(3) at cap) + RLIMIT_AS at 1.6x cap when
DuckDB tolerates it. Exit code 3 == clean cap abort (a SUCCESS by campaign
definition), harness records it and stops the ladder there.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import resource
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from omop_common import (FINAL_TABLES, MANIFEST, OMOP_VD_DIR, RESULTS_DIR,
                         SAMPLE_DRUG_SQLQUERY, _meminfo_snapshot,
                         _start_watchdog, peak_rss_mb, rss_mb)

DRUG_VD_STEMS = [
    "drug-exposure-medication-request-source-view",
    "drug-exposure-medication-statement-source-view",
    "drug-exposure-medication-administration-source-view",
    "drug-exposure-medication-dispense-source-view",
    "drug-exposure-immunization-source-view",
]

# Manifest `materialize` names -- the view names the sample SQLQuery's SQL
# references (e.g. omop.drug_exposure__medication_request).
MATERIALIZE = {
    "drug_exposure__medication_request":
        "drug-exposure-medication-request-source-view",
    "drug_exposure__medication_statement":
        "drug-exposure-medication-statement-source-view",
    "drug_exposure__medication_administration":
        "drug-exposure-medication-administration-source-view",
    "drug_exposure__medication_dispense":
        "drug-exposure-medication-dispense-source-view",
    "drug_exposure__immunization": "drug-exposure-immunization-source-view",
    "omop_conceptmap": "conceptmap-view",
}


def _try_setrlimit_as(cap_mb: float) -> bool:
    """RLIMIT_AS at 1.6x the RSS cap. DuckDB sometimes reserves large virtual
    arenas; if the connection then fails to open we retry without the limit
    and record that."""
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = int(cap_mb * 1.6 * 2**20)
        if hard != resource.RLIM_INFINITY and limit > hard:
            limit = hard
        resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
        return True
    except (ValueError, OSError):
        return False


def _ctas_exec(con, sql_from: str, reps: int, label: str) -> dict:
    """Median-of-reps CTAS execution. CTAS forces full evaluation (no column
    pruning); the result table is dropped between reps. Per-rep host
    meminfo is recorded so the report can PROVE reps ran in a swap-free
    window (MemAvailable floor + SwapFree guard, see _start_watchdog)."""
    times, rows, meminfo = [], 0, []
    for rep in range(reps):
        con.execute("DROP TABLE IF EXISTS _bench_result")
        snap = _meminfo_snapshot()
        t0 = time.perf_counter()
        con.execute(f"CREATE TABLE _bench_result AS SELECT * FROM {sql_from}")
        ms = (time.perf_counter() - t0) * 1000
        rows = con.execute("SELECT count(*) FROM _bench_result").fetchone()[0]
        times.append(round(ms, 1))
        meminfo.append(snap)
        print(f"  [{label}] rep{rep + 1}: {ms:,.1f}ms rows={rows:,} "
              f"rss={rss_mb():,.0f}MB peak={peak_rss_mb():,.0f}MB "
              f"host_avail={snap.get('MemAvailable_mb'):,.0f}MB "
              f"swap_free={snap.get('SwapFree_mb'):,.0f}MB", flush=True)
    con.execute("DROP TABLE IF EXISTS _bench_result")
    return {"exec_ms": times, "exec_ms_median": sorted(times)[len(times) // 2],
            "rows": rows, "host_meminfo_per_rep": meminfo}


def workload_omop(con, args) -> dict:
    from fhir4ds.viewdef.omop_runner import create_omop_views
    from fhir4ds.viewdef.runner import generate_view_sql

    # --- compile diagnostics: per-VD parse+generate, then view CREATEs
    gen_ms = {}
    for stem in sorted(p.stem for p in OMOP_VD_DIR.glob("*.json")
                       if p.name not in ("manifest.json",
                                         "conceptmap-supplements.json",
                                         "vocabulary.json")):
        t0 = time.perf_counter()
        generate_view_sql(OMOP_VD_DIR / f"{stem}.json", "resources")
        gen_ms[stem] = round((time.perf_counter() - t0) * 1000, 1)
    t0 = time.perf_counter()
    views = create_omop_views(con, "resources")
    compose_ms = (time.perf_counter() - t0) * 1000
    print(f"composition: {len(views)} views in {compose_ms:,.1f}ms", flush=True)

    # --- exec: one CTAS per source ViewDefinition (pure-VD view).
    # Skipped on --tables resume (already recorded in the partial JSON).
    SOURCE_VIEW_NAMES = {
        "drug-exposure-medication-request-source-view":
            "drug_exposure__medication_request",
        "drug-exposure-medication-statement-source-view":
            "drug_exposure__medication_statement",
        "drug-exposure-medication-administration-source-view":
            "drug_exposure__medication_administration",
        "drug-exposure-medication-dispense-source-view":
            "drug_exposure__medication_dispense",
        "drug-exposure-immunization-source-view":
            "drug_exposure__immunization",
        "conceptmap-view": "omop_conceptmap",
    }
    source_exec = {}
    _run_src = not getattr(args, "tables", None)
    for stem in (DRUG_VD_STEMS + [
            "person-source-view", "visit-occurrence-source-view",
            "condition-occurrence-source-view",
            "procedure-occurrence-source-view", "measurement-source-view",
            "observation-source-view", "device-exposure-source-view",
            "death-source-view", "conceptmap-view"]) if _run_src else []:
        name = SOURCE_VIEW_NAMES.get(
            stem, stem.replace("-view", "").replace("-", "_"))
        t0 = time.perf_counter()
        con.execute("DROP TABLE IF EXISTS _bench_src")
        con.execute(f'CREATE TABLE _bench_src AS SELECT * FROM omop."{name}"')
        ms = (time.perf_counter() - t0) * 1000
        rows = con.execute("SELECT count(*) FROM _bench_src").fetchone()[0]
        con.execute("DROP TABLE _bench_src")
        source_exec[stem] = {"exec_ms": round(ms, 1), "rows": rows}
        print(f"  [src:{name}] {ms:,.1f}ms rows={rows:,}", flush=True)

    # --- exec: final OMOP tables (SQLQuery-composed), median of reps.
    # Result JSON is saved incrementally so a watchdog abort (rc 3/5) still
    # leaves the completed tables on disk (resumability, 2026-11-03).
    final_exec = {}
    out_path = RESULTS_DIR / f"rung{args.patients}_omop.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tables = [t for t in FINAL_TABLES
              if not args.tables or t in args.tables.split(",")]
    if args.tables and out_path.exists():
        # resume: keep already-measured tables and the source-view record
        prior = json.loads(out_path.read_text())
        final_exec.update(prior.get("exec_final_tables", {}))
        source_exec = prior.get("exec_source_views", source_exec)
        gen_ms_prior = prior.get("compile", {}).get("vd_generate_ms", {})
        gen_ms = gen_ms if gen_ms else gen_ms_prior
        compose_ms = prior.get("compile", {}).get("view_create_ms",
                                                  compose_ms)
    partial = {
        "workload": "omop", "patients": args.patients,
        "compile": {"vd_generate_ms": gen_ms,
                    "view_create_ms": round(compose_ms, 1)},
        "exec_source_views": source_exec, "exec_final_tables": final_exec,
        "partial": len(final_exec) < len(FINAL_TABLES),
    }
    for t in tables:
        final_exec[t] = _ctas_exec(con, f'omop."{t}"', args.reps, t)
        out_path.write_text(json.dumps(partial, indent=2))

    return {
        "workload": "omop",
        "compile": {"vd_generate_ms": gen_ms,
                    "view_create_ms": round(compose_ms, 1)},
        "exec_source_views": source_exec,
        "exec_final_tables": final_exec,
        "rows_total": sum(v["rows"] for v in final_exec.values()),
    }


def workload_drug_sqlquery(con, args) -> dict:
    from fhir4ds.viewdef.runner import generate_view_sql, materialize_views
    from fhir4ds.sqlquery.parser import parse_library

    # --- compile diagnostics: generate + CREATE the 5 sample-backed views.
    # Table names mirror the manifest's `materialize` map (the names the
    # sample SQLQuery's SQL references, e.g. omop.drug_exposure__medication_request).
    t0 = time.perf_counter()
    gen_ms = {}
    for stem in MATERIALIZE.values():
        t1 = time.perf_counter()
        generate_view_sql(OMOP_VD_DIR / f"{stem}.json", "resources")
        gen_ms[stem] = round((time.perf_counter() - t1) * 1000, 1)
    for view_name, stem in MATERIALIZE.items():
        materialize_views(con, OMOP_VD_DIR, [stem], "resources",
                          schema="omop", table_name=view_name)
    compose_ms = (time.perf_counter() - t0) * 1000

    # --- SQLQuery parse via the spec machinery (diagnostic)
    lib_dict = json.loads(SAMPLE_DRUG_SQLQUERY.read_text())
    t0 = time.perf_counter()
    lib = parse_library(lib_dict)
    parse_ms = (time.perf_counter() - t0) * 1000
    body = lib.content[0].data  # parser pre-decodes application/sql

    # --- exec: CTAS of the sample SQLQuery body
    exec_rec = _ctas_exec(con, f"(\n{body}\n)", args.reps, "drug_sqlquery")

    # per-source-arm rows (which union arm dominates) - one pass, diagnostic
    arm_rows = {}
    for view_name in MATERIALIZE:
        if view_name == "omop_conceptmap":
            continue
        try:
            arm_rows[view_name] = con.execute(
                f'SELECT count(*) FROM omop."{view_name}"').fetchone()[0]
        except Exception as exc:
            arm_rows[view_name] = f"ERR {exc}"[:80]

    return {
        "workload": "drug_sqlquery",
        "compile": {"vd_generate_ms": gen_ms,
                    "view_create_ms": round(compose_ms, 1),
                    "sqlquery_parse_ms": round(parse_ms, 1),
                    "sql_chars": len(body)},
        "exec": exec_rec,
        "arm_rows": arm_rows,
        "rows_total": exec_rec["rows"],
    }


def capture_explain(con, sql: str, name: str, tag: str) -> dict:
    """EXPLAIN ANALYZE one statement; persist profile JSON + rendered tree."""
    prof_dir = RESULTS_DIR / "profiles"
    prof_dir.mkdir(parents=True, exist_ok=True)
    con.execute("SET enable_profiling='json'")
    try:
        t0 = time.perf_counter()
        rows = con.execute("EXPLAIN ANALYZE " + sql).fetchall()
        ms = (time.perf_counter() - t0) * 1000
    finally:
        con.execute("RESET enable_profiling")
    payload = json.loads(rows[0][1])

    def render(node, depth=0):
        lines = [f"{'  ' * depth}{node.get('operator_name') or '<root>'}"
                 f"  [{(node.get('operator_timing') or 0) * 1000:,.1f}ms]"
                 f" rows={node.get('operator_cardinality')}"]
        for ch in node.get("children") or []:
            lines.extend(render(ch, depth + 1))
        return lines

    (prof_dir / f"{tag}_{name}_profile.json").write_text(
        json.dumps(payload, indent=1))
    (prof_dir / f"{tag}_{name}_explain.txt").write_text(
        "\n".join(render(payload)) + "\n")
    return {"name": name, "explain_analyze_ms": round(ms, 1),
            "latency_ms": round((payload.get("latency") or 0) * 1000, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--workload", choices=["omop", "drug_sqlquery"],
                    required=True)
    ap.add_argument("--patients", type=int, required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--rss-cap-mb", type=float, default=24000.0)
    ap.add_argument("--duckdb-memory-limit", default="16GB")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--explain", action="store_true",
                    help="also capture EXPLAIN ANALYZE profiles")
    ap.add_argument("--explain-only", action="store_true")
    ap.add_argument("--out-suffix", default="",
                    help="append to the result JSON filename (variant tags)")
    ap.add_argument("--s3-endpoint", default=None)
    ap.add_argument("--s3-access-key", default=None)
    ap.add_argument("--s3-secret-key", default=None)
    ap.add_argument("--tables", default=None,
                    help="comma-separated subset of final tables (resume "
                         "after a clean abort; merges into the partial "
                         "result JSON)")
    ap.add_argument("--system-floor-mb", type=float, default=3072.0,
                    help="abort if host MemAvailable drops below this "
                         "(swap-free discipline)")
    args = ap.parse_args()

    _start_watchdog(args.rss_cap_mb, args.system_floor_mb)
    rlimit_ok = _try_setrlimit_as(args.rss_cap_mb)
    print(f"leg config: workload={args.workload} patients={args.patients} "
          f"cap={args.rss_cap_mb:,.0f}MB rlimit_as={rlimit_ok} "
          f"duckdb={args.duckdb_memory_limit} threads={args.threads}",
          flush=True)

    import fhir4ds
    try:
        con = fhir4ds.create_connection(database=args.db)
    except (MemoryError, OSError) as exc:
        print(f"RLIMIT_AS prevented connection ({exc}); retrying unlimited",
              flush=True)
        resource.setrlimit(resource.RLIMIT_AS, (resource.RLIM_INFINITY,
                                                resource.RLIM_INFINITY))
        rlimit_ok = False
        con = fhir4ds.create_connection(database=args.db)
    con.execute(f"SET threads={args.threads}")
    if args.s3_endpoint or args.s3_access_key:
        # AMUX-39 streaming: the rung view may point at s3:// chunks; the
        # SECRET is connection-scoped so every leg re-declares it.
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
        con.execute(
            "CREATE OR REPLACE SECRET __omop_s3 (TYPE S3, "
            + (f"KEY_ID '{args.s3_access_key}', "
               f"SECRET '{args.s3_secret_key}', "
               if args.s3_access_key else "")
            + (f"ENDPOINT '{args.s3_endpoint.split('://',1)[1]}', "
               if args.s3_endpoint else "")
            + "USE_SSL false, URL_STYLE 'path')")
    con.execute(f"SET memory_limit='{args.duckdb_memory_limit}'")
    _tmp = os.environ.get(
        "SCALING_TMPDIR", os.path.join(tempfile.gettempdir(), "fhir4ds_duckdb_tmp")
    )
    os.makedirs(_tmp, exist_ok=True)
    con.execute(f"SET temp_directory='{_tmp}'")

    tag = f"rung{args.patients}_{args.workload}"
    if args.explain_only:
        tag += "_explain"  # never clobber the timed result JSON
    if args.explain_only:
        rec = {"workload": args.workload + "_explain", "profiles": []}
        from fhir4ds.viewdef.omop_runner import create_omop_views
        if args.workload == "omop":
            create_omop_views(con, "resources")
            for t in ("drug_exposure", "observation", "person"):
                rec["profiles"].append(capture_explain(
                    con, f'SELECT * FROM omop."{t}"', t, tag))
        else:
            # the sample SQLQuery reads omop.drug_exposure__* views;
            # materialize them exactly as the timed leg does
            from fhir4ds.viewdef.runner import materialize_views
            for view_name, stem in MATERIALIZE.items():
                materialize_views(con, OMOP_VD_DIR, [stem], "resources",
                                  schema="omop", table_name=view_name)
            from fhir4ds.sqlquery.parser import parse_library
            lib = parse_library(json.loads(SAMPLE_DRUG_SQLQUERY.read_text()))
            body = lib.content[0].data
            rec["profiles"].append(capture_explain(con, body, "drug_sqlquery",
                                                   tag))
    elif args.workload == "omop":
        rec = workload_omop(con, args)
    else:
        rec = workload_drug_sqlquery(con, args)

    if args.explain and not args.explain_only:
        rec["profiles"] = [capture_explain(con, sql, name, tag)
                           for name, sql in _explain_targets(con, args)]

    rec.update({
        "patients": args.patients,
        "db": args.db,
        "reps": args.reps,
        "rss_cap_mb": args.rss_cap_mb,
        "rlimit_as_active": rlimit_ok,
        "duckdb_memory_limit": args.duckdb_memory_limit,
        "threads": args.threads,
        "peak_rss_mb": round(peak_rss_mb(), 1),
    })
    out = RESULTS_DIR / f"{tag}{args.out_suffix}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=2))
    print(json.dumps({k: rec[k] for k in
                      ("workload", "patients", "peak_rss_mb", "rows_total")
                      if k in rec}, indent=2), flush=True)
    print(f"saved {out}", flush=True)


def _explain_targets(con, args):
    if args.workload == "omop":
        return [(t, f'SELECT * FROM omop."{t}"')
                for t in ("drug_exposure", "observation")]
    lib_dict = json.loads(SAMPLE_DRUG_SQLQUERY.read_text())
    from fhir4ds.sqlquery.parser import parse_library
    body = parse_library(lib_dict).content[0].data
    return [("drug_sqlquery", body)]


if __name__ == "__main__":
    main()
