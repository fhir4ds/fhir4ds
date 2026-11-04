#!/usr/bin/env python3
"""Prepare one rung for measurement: a small DuckDB file whose `resources`
is a VIEW over the per-1000-patient zstd Parquet chunks (plus the constant
terminology parquet).

  python3 benchmarks/scaling/stage_omop_rung.py --patients 10000

Why a view, not a table (2026-11-03): DuckDB stores long JSON strings
UNCOMPRESSED (FSST cannot encode strings >2KB; FHIR resources exceed that),
so a materialized table costs ~1.8x the raw JSON text (measured: 10k
patients -> 8.1M resources -> 7.8GB JSON -> 14.4GB DuckDB file) while the
zstd Parquet chunks for the ENTIRE 114k-patient corpus are 3.8GB. The view
keeps data compressed on disk, decompressing on scan (part of exec, and
identical across rungs), and makes staging a ~1s metadata operation.

Staging wall time and peak RSS are recorded as diagnostics; they are never
part of exec metrics. Nested prefixes: rung N = chunks 0..ceil(N/1000)-1.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from omop_common import (CONVERTED, DB_DIR, RESULTS_DIR, _start_watchdog,
                         peak_rss_mb)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients", type=int, required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--elements-per-chunk", type=int, default=200)
    ap.add_argument("--rss-abort-mb", type=float, default=24000.0)
    ap.add_argument("--system-floor-mb", type=float, default=3072.0)
    ap.add_argument("--duckdb-memory-limit", default="8GB")
    ap.add_argument("--staging-suffix", default="",
                    help="append to the staging result JSON filename "
                         "(variant tags)")
    ap.add_argument("--chunk-prefix", default=None,
                    help="AMUX-39 streaming: read chunks from "
                         "s3://bucket/prefix or http(s)://host/prefix "
                         "instead of the local converted dir (DuckDB "
                         "httpfs)")
    ap.add_argument("--s3-endpoint", default=None)
    ap.add_argument("--s3-access-key", default=None)
    ap.add_argument("--s3-secret-key", default=None)
    args = ap.parse_args()

    _start_watchdog(args.rss_abort_mb, args.system_floor_mb)

    db_path = Path(args.db) if args.db else DB_DIR / f"rung{args.patients}.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    import duckdb

    meta = json.loads((CONVERTED / "chunks.json").read_text())
    n_chunks = min((args.patients + meta["chunk_size"] - 1)
                   // meta["chunk_size"], meta["n_chunks"])
    assert n_chunks * meta["chunk_size"] >= args.patients, \
        "converted corpus smaller than requested rung"
    if args.chunk_prefix:
        prefix = args.chunk_prefix.rstrip("/")
        chunk_files = [f"{prefix}/chunk_{i:05d}.parquet"
                       for i in range(n_chunks)]
        term = f"{prefix}/terminology.parquet"
    else:
        chunk_files = [str(CONVERTED / f"chunk_{i:05d}.parquet")
                       for i in range(n_chunks)]
        term = str(CONVERTED / "terminology.parquet")

    if db_path.exists():
        db_path.unlink()
    t0 = time.perf_counter()
    con = duckdb.connect(str(db_path))
    con.execute(f"SET memory_limit='{args.duckdb_memory_limit}'")
    if args.chunk_prefix and args.chunk_prefix.startswith("s3://"):
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
        if args.s3_endpoint or args.s3_access_key:
            con.execute(
                "CREATE OR REPLACE SECRET __omop_s3 (TYPE S3, "
                + (f"KEY_ID '{args.s3_access_key}', "
                   f"SECRET '{args.s3_secret_key}', "
                   if args.s3_access_key else "")
                + (f"ENDPOINT '{args.s3_endpoint.split('://',1)[1]}', "
                   if args.s3_endpoint else "")
                + "USE_SSL false, URL_STYLE 'path')")
    # CREATE VIEW cannot be prepared — inline the (harness-controlled, safe)
    # file lists as literals.
    chunk_lit = ", ".join("'" + f.replace("'", "''") + "'" for f in chunk_files)
    term_lit = "'" + term.replace("'", "''") + "'"
    con.execute(
        "CREATE VIEW resources AS "
        f"SELECT resource FROM read_parquet([{chunk_lit}]) "
        f"UNION ALL SELECT resource FROM read_parquet([{term_lit}])")
    n_rows, json_bytes = con.execute(
        "SELECT count(*), sum(length(resource)) FROM resources").fetchone()
    counts = dict(con.execute(
        "SELECT json_extract_string(resource, '$.resourceType') rt, count(*) "
        "FROM resources GROUP BY 1 ORDER BY 2 DESC").fetchall())
    n_pat = counts.get("Patient", 0)
    con.execute("CHECKPOINT")
    con.close()
    stage_s = time.perf_counter() - t0

    if args.chunk_prefix:
        # remote: sizes via DuckDB parquet metadata (one HEAD per file,
        # cheap) — or leave None if unreachable
        corpus_mb = None  # sizes via object store HEAD; not load-bearing
    else:
        corpus_mb = sum(Path(f).stat().st_size for f in chunk_files) / 2**20
    record = {
        "patients_requested": args.patients,
        "patients_actual": n_pat,
        "resources": n_rows,
        "type_counts": counts,
        "json_bytes_staged": json_bytes,
        "parquet_corpus_mb": round(corpus_mb, 1) if corpus_mb else None,
        "db_file_mb": round(db_path.stat().st_size / 2**20, 3),
        "stage_wall_s": round(stage_s, 1),
        "stage_peak_rss_mb": round(peak_rss_mb(), 1),
        "db_path": str(db_path),
        "staging_path": "parquet-view",
        "chunks": n_chunks,
    }
    out = RESULTS_DIR / f"rung{args.patients}_staging{args.staging_suffix}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
