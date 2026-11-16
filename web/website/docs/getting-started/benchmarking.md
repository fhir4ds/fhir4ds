---
id: benchmarking
title: Benchmarking & Accuracy
description: "FHIR4DS query and translation benchmarks against reference FHIRPath implementations, with reproducible methodology."
---

# Benchmarking & Accuracy

FHIR4DS is rigorously tested against the official CMS eCQM test bundles from the [ecqm-content-qicore-2025](https://github.com/cqframework/ecqm-content-qicore-2025) package. These are the same industry-standard test datasets used to certify all conformant clinical reasoning engines.

## 1. Accuracy Results

FHIR4DS achieves **100% spec compliance** across all test suites — 2,943 total tests passing.

| Metric | Result |
|--------|-----------------|
| **CQL** | **100%** (1,706 / 1,706 tests) |
| **FHIRPath** | **100%** (935 / 935 tests) |
| **SQL-on-FHIR** | **100%** (144 / 144 tests) |
| **eCQMs (2025 QI-Core suite)** | **100% pass rate** (47 / 47) |
| **DQMs (2025 US-Core suite)** | **100% pass rate** (73 / 73) |

### Known Upstream Accuracy Gaps
4 measures have documented accuracy gaps caused by bugs in the official CMS test bundles, not by FHIR4DS implementation errors. These measures fail equally in all conformant engines.

| Measure | Issue in Upstream Test Data |
|---------|-----------------------------|
| **CMS135** | Heart Failure — MADIE-2124: MeasureReport has denominator-exception=0 for DENEXCEPPass test cases |
| **CMS145** | IVF — MADIE-2124: Same pattern as CMS135 |
| **CMS157** | Oncology — Test data has 2025 encounter dates but measurement period is 2026 |
| **CMS1017** | Palliative Care — Non-UUID IDs, contradictory MeasureReports, missing valueset codes |

---

## 2. Performance & Throughput

By leveraging a SQL-native, vectorized architecture, FHIR4DS provides a transformative performance advantage over traditional engines.

### Head-to-Head: FHIR4DS vs. Java Reference Engine

We compared FHIR4DS against the industry-standard [Java Clinical Reasoning](https://github.com/cqframework/clinical-reasoning) engine on the **cqframework 2025 QI-Core test bundles**. 46 of 47 measures succeed in both engines; the head-to-head below covers that shared set of 46 measures (per-patient execution time only).

| Metric | Traditional Engine (Java) | FHIR4DS (DuckDB 2.0.0) | Speedup |
|--------|---------------------------|-------------------------|---------|
| **Median Execution/Patient** | ~575ms | **~6.9ms** | **~83×** |

Across all 47 measures of the 2025 QI-Core suite, FHIR4DS executes at a median of ~6.9ms per patient on DuckDB 2.0.0 (the recommended engine; `fhir4ds.register()` automatically applies the validated `delim_join_as_cte=false` planner tuning on DuckDB 2.x). We report the median rather than the mean because a small heavy tail inflates the mean (~15ms) — the three most expensive measures (CMS117 ~92ms, CMS128 ~89ms, CMS0334 ~70ms per patient) run well above the typical measure on these small test cohorts. Compile phases are one-time diagnostics at deploy (not included in the per-patient figures): ~15ms parse and ~476ms SQL translation per library.

> **DuckDB 1.5.6 footnote:** on the same per-patient test cohorts (tens to low hundreds of patients), DuckDB 1.5.6 measured a median of ~4.5ms (mean ~11.9ms), i.e. ~131× median / ~39× mean vs Java. On these tiny cohorts, DuckDB 2.0's per-query overhead makes it slightly slower than 1.5.6; the tables turn decisively at population scale (see the scaling ladder below, where 2.0 is ~10× faster on CMS130/CMS133 at 5,000 patients).

### Scalability

The speedup reflects the architectural difference: traditional engines evaluate each patient sequentially, whereas FHIR4DS runs a single columnar SQL query that processes the entire population simultaneously. The per-patient cost is dominated by correctness and audit machinery, and the marginal per-patient cost falls as the cohort grows.

Java baseline numbers at scale are a per-patient linear extrapolation from the head-to-head measurement above, unchanged from the prior measurement.

### Scaling Ladder (Synthea synthetic patients)

Measured on **Synthea synthetic patients** (distinct from the cqframework 2025 QI-Core test bundles used for the head-to-head above), with nested deterministic prefixes, measurement period 2026, in-memory **DuckDB 2.0.0** with the automatic planner tuning, median of 3 runs. The top rung covers 6.28M resources.

| Measure | 100 patients | 1,000 patients | 5,000 patients |
|---------|-------------|----------------|----------------|
| **CMS68** | 45ms | 88ms | 225ms |
| **CMS22** | 948ms | 1,863ms | 5,074ms |
| **CMS2** | 1,118ms | 1,377ms | 2,706ms |
| **CMS130** | 816ms | 1,654ms | 5,576ms |
| **CMS133** | 606ms | 1,287ms | 5,166ms |

Peak RSS at 5,000 patients: ~20 GB. CMS68 at 5,000 patients runs at **0.045ms per patient** — evidence of population-level amortization: a single scan's fixed cost is spread across the whole cohort.

> **DuckDB 1.5.6 footnote (@5,000 patients):** CMS68 474ms, CMS22 4,630ms, CMS2 2,773ms, CMS130 57,357ms, CMS133 46,428ms. DuckDB 2.0.0 is roughly **10× faster on CMS130 and CMS133** at this rung — the planner improvements in 2.0 compound with population scale.

---

## 3. Measures Tested

The 47 CMS eCQMs from the 2025 QI-Core content package included in our standard benchmark suite include:

- **CMS74** — Primary Caries Prevention
- **CMS75** — Children with Dental Decay
- **CMS124** — Cervical Cancer Screening
- **CMS130** — Colorectal Cancer Screening
- **CMS159** — Depression Remission
- **CMS349** — HIV Screening
- ... and 41 additional measures.

---

## 4. Running Benchmarks Locally

To verify these results in your own environment, you can run the benchmark suite directly from the repository:

```bash
# Navigate to the benchmarking directory
cd benchmarks

# Run the full 2025 QI-Core suite
python -m runner --suite 2025 --skip-errors
```

## 5. CI Performance Reports

The repository also includes a DQM timing report workflow for tracking
performance changes across the 2025 measure suite. The workflow runs the DQM
conformance suite, compares `conformance/reports/dqm_report.json` to the
checked-in baseline at `benchmarks/baselines/dqm_2025.json`, and uploads JSON
and Markdown reports as GitHub Actions artifacts.

To generate the same report locally:

```bash
python3 conformance/scripts/run_dqm.py
python3 benchmarks/runner/dqm_perf_report.py \
  --current conformance/reports/dqm_report.json \
  --baseline benchmarks/baselines/dqm_2025.json \
  --output-json benchmarks/output/dqm-performance-report.json \
  --output-md benchmarks/output/dqm-performance-report.md
```

See the repository's `CONTRIBUTING.md` and `.github/CI.md` files for workflow behavior and baseline update policy.
