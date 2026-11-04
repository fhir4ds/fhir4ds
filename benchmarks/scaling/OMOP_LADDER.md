# OMOP v5.5 ViewDefinition / SQLQuery scaling ladder

Campaign 2026-11-02..03 (Joel): 1k → 10k → 100k Synthea patients, OMOP v5.5
ViewDefinition set + the drug-exposure SQLQuery sample. Exec-only headline
metrics, peak-RSS probing toward the ceiling with a hard cap, EXPLAIN-derived
optimisation candidates.

## Measurement discipline (2026-11-03 revisions, after Joel's reviews)

1. **Swap-free windows only.** Host swap-inflated numbers are not
   measurements (rep drift 477s→707s observed on the polluted 100k attempt).
   Every leg now: (a) gates at launch on host `MemAvailable` ≥ 12GB AND
   `SwapFree` ≥ 3GB, (b) self-aborts (exit 5) if `MemAvailable` < 3GB or
   `SwapFree` < 1GB mid-run, and (c) records per-rep meminfo snapshots in
   its result JSON as post-hoc proof the reps ran clean.
2. **Parquet-backed source view, no materialized table.** DuckDB stores
   long JSON strings UNCOMPRESSED (FSST cannot encode strings >2KB; FHIR
   resources exceed that): a materialized 10k-patient table was 14.4GB vs
   7.8GB of raw JSON, and the whole 114k-patient zstd Parquet corpus is
   3.8GB. The staged rung db is now a 0.3MB file whose `resources` is a
   VIEW over the chunk parquets (staging = ~2s). Consequence: every scan
   pays zstd decode (honest cold-scan condition, identical at every rung).
   The earlier materialized-table numbers at 1k/10k silently benefited
   from the whole table sitting in DuckDB's buffer pool — a cache that is
   physically impossible at 100k, so the view keeps all rungs comparable.
3. **8GB DuckDB memory_limit** at every rung (bounded working set on the
   shared 62GB host; DuckDB spills to its own temp dir, which is
   controlled and measurable, unlike host swap).

## One command

```bash
# after the corpus exists (see below):
python3 benchmarks/scaling/run_omop_ladder.py --duckdb-memory-limit 8GB
# == --rungs 1000,10000,100000 --workloads omop,drug_sqlquery --reps 3
```

Per rung the driver: checks corpus availability → stages `db/rung<N>.duckdb`
(if missing) → pre-flight RSS projection (calibrated from the previous rung;
a leg projecting above `--rss-cap-mb` is SKIPPED and recorded, and the
fallback rung logic is documented in its output) → leg A (OMOP composition)
→ leg B (drug-exposure SQLQuery sample) → EXPLAIN ANALYZE legs (rungs ≤
`--explain-max-patients`). Results land in
`benchmarks/scaling/results/omop/`, report via:

```bash
python3 benchmarks/scaling/make_omop_report.py   # -> benchmarks/baselines/omop_v55_scaling_2026.md
```

## Workloads

- **A — `omop`**: the full OMOP v5.5 composition
  (`fhir4ds/viewdef/resources/omop/manifest.json` via
  `fhir4ds.viewdef.omop_runner.create_omop_views`). Exec = CTAS
  (`CREATE TABLE ... AS SELECT *`) of each of the 9 final OMOP tables,
  median of 3 reps, plus one CTAS per source ViewDefinition (the pure-VD
  view of the same data). CTAS forces full evaluation — `count(*)` over a
  view would let DuckDB prune the expensive fhirpath columns.
- **B — `drug_sqlquery`**: the shipped sample
  `web/viewing-room/public/samples/omop-drug-exposure-sqlquery/` — 5
  drug-exposure source views + `omop.omop_conceptmap` materialized with the
  manifest's exact view names, the sample Library parsed through
  `fhir4ds.sqlquery` (spec machinery; diagnostic), then exec = CTAS of the
  sample query body, median of 3 reps.

Compile (parse / SQL generation / CREATE VIEW) is timed separately and is
never folded into exec figures. Staging is a separate once-per-rung phase.

## Corpus (durable, /mnt/d/scaling-data/omop-scaling)

```bash
# 1. Synthea 100k patients (seed 20261102; ~3.5 h; OMOP-consumed types only
#    via exporter.fhir.included_resources; per-patient bundles):
cd /mnt/d/scaling-data/omop-scaling/s100k && \
  java -Xmx8g -jar ../synthea-with-deps.jar -p 100000 -s 20261102

# 2. Convert to per-1000-patient Parquet chunks (local ext4; fast re-staging;
#    nested prefixes: rung 1k = chunk 0, 10k = chunks 0..9, 100k = all):
python3 benchmarks/scaling/convert_corpus.py --workers 8
```

Rung corpora are deterministic nested prefixes: sorted patient bundle files
minus `*information*`. Terminology is constant at every rung: the HF
`fhir4ds/omop-demo` monolithic ConceptMap (RxNorm 108,421 + CVX 255 elements)
chunked at 200 elements/chunk + `conceptmap-supplements.json` for the small
groups (gender / ActCode / condition-category — do NOT also chunk those
groups from the monolithic map: double-staging fans `person` to 2 rows per
patient).

## Memory discipline (mandatory)

Each leg is a fresh subprocess with: an RSS watchdog (`os._exit(3)` at
`--rss-cap-mb`, exit 3 = clean cap abort = campaign SUCCESS), a SYSTEM
floor watchdog (`os._exit(5)` when host MemAvailable < 3GB or SwapFree <
1GB — stop before polluting the measurement), RLIMIT_AS at 1.6× cap when
DuckDB tolerates it, and a DuckDB `memory_limit` below the cap with
`temp_directory` spill. The parent refuses to launch into a swap-risk
window (MemAvailable ≥ 12GB and SwapFree ≥ 3GB required) and records where
the ladder stopped and why. The 2026-10-28 host freeze (58.7 GB RSS on a
62 GB box) is the failure mode this prevents.

## AMUX-39: streaming/chunked S3 support (verified 2026-11-03)

The chunk corpus is S3-native: rungs read Parquet chunks over httpfs with
the same memory-guard harness.

```bash
# 1. push the converted chunks to any S3-compatible endpoint
python3 benchmarks/scaling/s3_push.py s3://bucket/chunks \
    [--endpoint-url http://s3.local:9000 --access-key ... --secret-key ...]

# 2. stage a rung whose `resources` view streams off S3
python3 benchmarks/scaling/stage_omop_rung.py --patients 1000 \
    --chunk-prefix s3://bucket/chunks [--s3-endpoint ... --s3-access-key ...]

# 3. measured legs need the (connection-scoped) SECRET re-declared:
python3 benchmarks/scaling/omop_leg.py --db rung.duckdb \
    --workload drug_sqlquery ... --s3-endpoint ... --s3-access-key ...

# 4. one-shot A/B verification through the memory-guard harness:
python3 benchmarks/scaling/run_s3_stream_check.py --patients 1000 \
    --prefix s3://bucket/chunks --endpoint ... --access-key ... --secret-key ...
```

Verified against a local `rclone serve s3` endpoint (real S3v4 signing +
range GETs; 3.8GB / 117 objects pushed): S3-staged rungs are byte-identical
to local staging; warm streaming exec is at parity with local disk (±2%),
peak RSS unchanged (774MB vs 770MB — the memory profile is bounded by the
DuckDB `memory_limit` regardless of source); the first cold pass costs ~4×
(ranged-GET fetch amortization). Results:
`results/omop/s3_stream_check_1000.json`.

## Files

- `omop_common.py` — paths, corpus slicing, terminology prep, watchdogs,
  leg runner with the swap-free launch gate
- `convert_corpus.py` — Synthea bundles → Parquet chunks (+ terminology)
- `s3_push.py` — AMUX-39: push chunks to an S3-compatible endpoint
- `stage_omop_rung.py` — rung prep (parquet-backed `resources` view;
  `--chunk-prefix s3://` for streaming)
- `omop_leg.py` — measured workloads + EXPLAIN capture (self-guarded child;
  S3 secret re-declaration for streaming rungs)
- `run_omop_ladder.py` — the one-command driver with pre-flight gating
- `run_s3_stream_check.py` — AMUX-39 streaming-vs-local A/B verification
- `make_omop_report.py` — results JSONs → markdown baseline report
