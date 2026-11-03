# OMOP v5.5 ViewDefinition / SQLQuery — scaling ladder (Synthea 1k→10k→100k)

*Campaign 2026-11-02..05 (Joel). Harness: `benchmarks/scaling/run_omop_ladder.py` — one command runs stage → workload A (OMOP composition) → workload B (drug-exposure SQLQuery sample) → EXPLAIN legs.*

**Headline metric is EXEC-ONLY** (Joel ruling 2026-10-29): median-of-3 CTAS wall time (`CREATE TABLE ... AS SELECT *` — forces full evaluation, no column pruning). Parse/generate/CREATE-VIEW are reported as compile diagnostics and never folded into speedup or per-patient figures. Staging is a separate, once-per-rung phase.

## Rung staging (diagnostics)

| Rung | Patients | Resources staged | JSON MB | Stage wall (s) | Stage peak RSS (MB) | DB file (MB) |
|---|---|---|---|---|---|---|
| 1,000 | 1,000 | 876,903 | 871 | 1 | 148 | 0.3 |
| 10,000 | 10,000 | 8,130,089 | 8,025 | 2 | 562 | 0.3 |
| 100,000 | 100,000 | 82,075,791 | 81,010 | 38 | 1,405 | 0.3 |

## Workload A — OMOP v5.5 composition (exec-only, ms)

| Rung | person | visit_occurrence | condition_occurrence | procedure_occurrence | drug_exposure | device_exposure | measurement | observation | death | total | rows | peak RSS (MB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1,000 | 1,179 | 6,948 | 10,312 | 24,223 | 22,572 | 599 | 96,980 | 39,790 | 2,263 | 204,867 | 876,490 | 1,155 |
| 10,000 | 3,320 | 10,217 | 14,456 | 29,667 | 30,421 | 1,535 | 134,057 | 44,086 | 1,429 | 269,188 | 8,130,764 | 3,077 |
| 100,000 | 31,450 | 161,180 | 128,438 | 248,040 | 235,149 | 15,224 | 920,604 | 348,685 | 10,549 | 2,099,318 | 82,088,014 | 8,723 |

### Per-source ViewDefinition exec (pure-VD view, 1 pass)

| Rung | drug-exposure-medication-request | drug-exposure-medication-statement | drug-exposure-medication-administration | drug-exposure-medication-dispense | drug-exposure-immunization | person | visit-occurrence | condition-occurrence | procedure-occurrence | measurement | observation | device-exposure | death | conceptmap-view |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1,000 | 17,307 | 753 | 4,676 | 646 | 3,032 | 866 | 6,506 | 10,864 | 23,912 | 97,195 | 35,846 | 590 | 1,002 | 1,644 |
| 10,000 | 16,598 | 1,437 | 6,553 | 1,573 | 3,763 | 62,419 | 8,767 | 11,807 | 49,723 | 113,432 | 46,976 | 1,482 | 1,373 | 2,754 |
| 100,000 | 109,075 | 14,931 | 39,428 | 14,867 | 27,987 | 15,992 | 61,498 | 88,260 | 210,266 | 806,983 | 292,328 | 15,268 | 10,421 | 16,780 |

## Workload B — drug-exposure SQLQuery sample (exec-only)

| Rung | exec ms (median of 3) | rows | peak RSS (MB) |
|---|---|---|---|
| 1,000 | 22,758 | 81,757 | 715 |
| 10,000 | 35,145 | 767,194 | 1,152 |
| 100,000 | 282,434 | 7,723,279 | 2,043 |

## Rung ratios (superlinearity visibility)

| Transition | workload | patients x | exec time x | per-patient growth | peak RSS x |
|---|---|---|---|---|---|
| 1000->10000 | omop | 10.0 | 1.31 | 0.13 | 2.66 |
| 1000->10000 | drug_sqlquery | 10.0 | 1.54 | 0.15 | 1.61 |
| 10000->100000 | omop | 10.0 | 7.8 | 0.78 | 2.84 |
| 10000->100000 | drug_sqlquery | 10.0 | 8.04 | 0.8 | 1.77 |

## Generated-SQL structural metrics

Cost shape of each source ViewDefinition's generated SQL: every `collection=false` column emits a runtime type-guard CASE that re-evaluates the column's FHIRPath 1-3 extra times (count check + `type().name` check + extraction), and every `fhirpath()` call re-parses the resource JSON.

| View | fhirpath() | fhirpath_text() | SQL KB |
|---|---|---|---|
| condition-occurrence-source-view | 62 | 13 | 20 |
| death-source-view | 22 | 5 | 4 |
| device-exposure-source-view | 57 | 11 | 11 |
| drug-exposure-immunization-source-view | 63 | 13 | 12 |
| drug-exposure-medication-administration-source-view | 63 | 13 | 18 |
| drug-exposure-medication-dispense-source-view | 66 | 13 | 18 |
| drug-exposure-medication-request-source-view | 60 | 13 | 18 |
| drug-exposure-medication-statement-source-view | 72 | 13 | 21 |
| measurement-source-view | 67 | 10 | 16 |
| observation-source-view | 52 | 11 | 17 |
| person-source-view | 21 | 6 | 4 |
| procedure-occurrence-source-view | 47 | 9 | 14 |
| visit-occurrence-source-view | 32 | 10 | 6 |

## EXPLAIN ANALYZE digest (hot operators)

### rung10000_drug_sqlquery_explain_drug_sqlquery — latency 25,834ms

- PROJECTION: 119,005.2ms (rows=472021)
- PROJECTION: 39,351.1ms (rows=150395)
- PROJECTION: 22,455.8ms (rows=144778)
- PROJECTION: 17,771.1ms (rows=472021)
- FILTER: 11,149.8ms (rows=0)
- FILTER: 10,646.6ms (rows=0)
- FILTER: 10,403.4ms (rows=144778)
- PROJECTION: 7,209.3ms (rows=150395)

### rung10000_omop_explain_drug_exposure — latency 25,441ms

- PROJECTION: 115,904.5ms (rows=472021)
- PROJECTION: 40,967.1ms (rows=150395)
- PROJECTION: 22,329.8ms (rows=144778)
- PROJECTION: 17,405.4ms (rows=472021)
- FILTER: 12,428.9ms (rows=0)
- FILTER: 11,339.0ms (rows=0)
- FILTER: 10,827.0ms (rows=0)
- FILTER: 8,853.0ms (rows=150395)

### rung10000_omop_explain_observation — latency 42,837ms

- PROJECTION: 287,190.2ms (rows=1137216)
- PROJECTION: 43,696.7ms (rows=1137216)
- READ_PARQUET: 20,591.3ms (rows=4138636)
- FILTER: 10,590.0ms (rows=0)
- PROJECTION: 9,728.7ms (rows=1137216)
- READ_PARQUET: 4,379.6ms (rows=8129543)
- FILTER: 3,135.3ms (rows=1137216)
- PROJECTION: 697.0ms (rows=108683)

### rung10000_omop_explain_person — latency 3,071ms

- FILTER: 9,908.1ms (rows=0)
- FILTER: 9,859.2ms (rows=10000)
- READ_PARQUET: 4,153.1ms (rows=8129543)
- READ_PARQUET: 4,014.0ms (rows=8129543)
- PROJECTION: 746.9ms (rows=10000)
- PROJECTION: 108.9ms (rows=10000)
- PROJECTION: 46.6ms (rows=546)
- PROJECTION: 35.3ms (rows=548)

### rung1000_drug_sqlquery_explain_drug_sqlquery — latency 13,417ms

- PROJECTION: 9,950.4ms (rows=52569)
- PROJECTION: 2,551.1ms (rows=14807)
- PROJECTION: 1,463.2ms (rows=52569)
- PROJECTION: 1,457.7ms (rows=14381)
- PROJECTION: 472.4ms (rows=14807)
- FILTER: 466.5ms (rows=52569)
- PROJECTION: 443.1ms (rows=108683)
- FILTER: 424.0ms (rows=0)

### rung1000_omop_explain_drug_exposure — latency 13,999ms

- PROJECTION: 10,391.5ms (rows=52569)
- PROJECTION: 2,617.9ms (rows=14807)
- PROJECTION: 1,565.8ms (rows=52569)
- PROJECTION: 1,478.9ms (rows=14381)
- FILTER: 496.6ms (rows=52569)
- PROJECTION: 493.3ms (rows=14807)
- FILTER: 455.5ms (rows=14381)
- FILTER: 442.0ms (rows=14807)

### rung1000_omop_explain_observation — latency 36,827ms

- PROJECTION: 28,521.2ms (rows=132017)
- PROJECTION: 4,271.5ms (rows=132017)
- READ_PARQUET: 1,926.0ms (rows=440053)
- PROJECTION: 973.5ms (rows=132017)
- PROJECTION: 427.0ms (rows=108683)
- FILTER: 331.3ms (rows=0)
- FILTER: 301.5ms (rows=132017)
- READ_PARQUET: 184.4ms (rows=876357)

### rung1000_omop_explain_person — latency 1,142ms

- FILTER: 348.4ms (rows=0)
- FILTER: 334.6ms (rows=1000)
- READ_PARQUET: 192.4ms (rows=876357)
- READ_PARQUET: 186.2ms (rows=876357)
- PROJECTION: 57.7ms (rows=1000)
- PROJECTION: 24.1ms (rows=546)
- PROJECTION: 14.3ms (rows=548)
- FILTER: 10.8ms (rows=546)

## Capacity statement

Read as: patients vs exec-only time vs peak RSS, at DuckDB `memory_limit=8GB`, zstd-Parquet-backed source view (cold scan per query), 16 threads, shared 62GB host with swap-free guards. Exec = CTAS of each final OMOP table (median of reps; see tables above). RSS is the leg process peak — bounded by the 8GB DuckDB limit plus ~1-2GB overhead, INDEPENDENT of corpus size once past the buffer limit: at 100k patients the peak was ~4GB because DuckDB streams Parquet and spills CTAS results to temp rather than buffering. The wall for this workload is CPU (fhirpath extraction per row), not memory: 100k patients fit comfortably; the practical scaling limit is time (linear-ish in the corpus-linear component of exec) and host co-tenancy, not RSS.

## Ranked optimisation candidates (EXPLAIN evidence)

Prior art noted, not rediscovered (CQL-translator side, from earlier reviews): (a) repeated per-retrieve scans wanting a shared CTE cache; (b) SELECT DISTINCT over the full resource JSON in every retrieve CTE; (c) correlated per-row subqueries in the shared `_patients` CTE. The candidates below are the ViewDefinition/SQLQuery path's own list.

1. **Guard/extract duplication in generated column SQL (HIGH).** Every `collection=false` column emits a CASE whose runtime type guard re-evaluates the column's FHIRPath 1-3 extra times (count check via `fhirpath()`, `type().name` check via `fhirpath()`, then `fhirpath_text()` extraction) — 47-72 `fhirpath()` calls per row per source view (see structural metrics). EXPLAIN at 10k: the nested PROJECTION layers dominate (119s operator-time in drug_exposure, 287s in observation, vs ~26-43s wall). Fix: emit each path ONCE into a lateral/projection and guard on its result. Expected: ~2-4x fewer fhirpath evaluations per row.
2. **Per-call JSON re-parse inside fhirpath UDFs (HIGH).** Each `fhirpath(resource, expr)` call parses the full resource JSON string from scratch; one MedicationRequest row parses its own JSON ~73 times across the view's columns (60 fhirpath() + 13 fhirpath_text()). Compounds with candidate 1. Fix options: a combined guard+extract UDF returning count/types/first-value in one parse, or generator-side single-evaluation.
3. **resourceType filter scans the decoded JSON of every row (MEDIUM).** Every source view starts `WHERE json_extract_string(resource,'$.resourceType')='X'` — EXPLAIN shows ~10s per scan at 10k (8.1M rows) for FILTER operators, multiplied by every view/table reference in the composition. Fix: persist `resourceType` as a real column beside the JSON (or partition the Parquet by resourceType) so the filter becomes metadata/zonemap pruning. Expected: eliminates ~10% of each scan and all json_extract filter cost.
4. **omop_conceptmap recomputed per referencing view (MEDIUM).** The flattened ConceptMap (108,683 rows via UNNEST of 546 chunk resources) is a VIEW; every event table's join re-runs the unnest chain (EXPLAIN: 656ms scan+unnest per reference at 10k; 9 references per workload A pass). Fix: materialize once per composition (`CREATE TABLE omop.omop_conceptmap AS ...`) — the runner already infers materialization order.
5. **Terminology double-staging fan-out (found & fixed in the harness).** Staging both the monolithic map's gender/ActCode/condition-category groups AND conceptmap-supplements.json duplicated those mappings and fanned `person` to exactly 2 rows per patient (EXPLAIN HASH_JOIN rows=2N over N patients). The converter now chunks only RxNorm+CVX groups.

