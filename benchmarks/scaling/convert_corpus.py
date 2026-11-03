#!/usr/bin/env python3
"""Convert the Synthea s100k corpus into per-1000-patient Parquet chunks.

  python3 benchmarks/scaling/convert_corpus.py [--workers 8]

Output: /home/jmontavon/omop-scaling-db/converted/
  chunk_{i:05d}.parquet   -- `resource` string column, 1000 patients each,
                            OMOP-consumed types only, patient-sorted order
  terminology.parquet     -- chunked ConceptMap + supplements (constant)
  chunks.json             -- {chunk_size, n_chunks, patients_per_chunk[]}

Rung staging then becomes a native `CREATE TABLE ... AS SELECT ... FROM
read_parquet(...)` over the first N/1000 chunks — no Python row loop, no
drvfs reads, minutes instead of hours at the 100k rung, and perfectly
nested prefixes (rung 1k = chunk 0, 10k = chunks 0..9, 100k = all).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from omop_common import (DB_DIR, OMOP_RESOURCE_TYPES, SYNTHEA_DIR,
                         terminology_files)

CONVERTED = DB_DIR / "converted"
CHUNK = 1000


def convert_chunk(job: tuple[int, list[str], str]) -> tuple[int, int, int]:
    idx, files, out_path = job
    import pyarrow as pa
    import pyarrow.parquet as pq
    rows: list[str] = []
    n_pat = 0
    for path in files:
        try:
            bundle = json.load(open(path, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        n_pat += 1
        for entry in bundle.get("entry", []):
            r = entry.get("resource")
            if isinstance(r, dict) and r.get("resourceType") in \
                    OMOP_RESOURCE_TYPES:
                rows.append(json.dumps(r, separators=(",", ":")))
    table = pa.table({"resource": pa.array(rows, type=pa.string())})
    pq.write_table(table, out_path, compression="zstd")
    return idx, n_pat, len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--start-chunk", type=int, default=0)
    args = ap.parse_args()

    CONVERTED.mkdir(parents=True, exist_ok=True)
    files = sorted(
        str(SYNTHEA_DIR / f) for f in os.listdir(SYNTHEA_DIR)
        if f.endswith(".json") and "information" not in f.lower())
    n_chunks = (len(files) + CHUNK - 1) // CHUNK
    print(f"{len(files):,} patient bundles -> {n_chunks} chunks of {CHUNK}",
          flush=True)

    jobs = []
    for i in range(args.start_chunk, n_chunks):
        out = CONVERTED / f"chunk_{i:05d}.parquet"
        if out.exists():
            continue
        jobs.append((i, files[i * CHUNK:(i + 1) * CHUNK], str(out)))

    t0 = time.perf_counter()
    done_rows = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for idx, n_pat, n_rows in pool.map(convert_chunk, jobs):
            done_rows += n_rows
            el = time.perf_counter() - t0
            print(f"  chunk {idx} ({n_pat} patients, {n_rows:,} resources) "
                  f"total={done_rows:,} {el:,.0f}s", flush=True)

    # terminology parquet (constant across rungs)
    import pyarrow as pa
    import pyarrow.parquet as pq
    term_rows: list[str] = []
    for tf in terminology_files():
        term_rows += [l.strip() for l in open(tf, encoding="utf-8")
                      if l.strip()]
    pq.write_table(pa.table({"resource": pa.array(term_rows,
                                                  type=pa.string())}),
                   CONVERTED / "terminology.parquet", compression="zstd")

    meta = {"chunk_size": CHUNK, "n_chunks": n_chunks,
            "patients": len(files)}
    (CONVERTED / "chunks.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    main()
