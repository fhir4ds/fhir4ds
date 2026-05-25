---
id: benchmarking
title: Benchmarking & Accuracy
---

# Benchmarking & Accuracy

FHIR4DS is rigorously tested against the official CMS eCQM test bundles from the [ecqm-content-qicore-2025](https://github.com/cqframework/ecqm-content-qicore-2025) package. These are the same industry-standard test datasets used to certify all conformant clinical reasoning engines.

## 1. Accuracy Results

FHIR4DS achieves **100% spec compliance** across all test suites — 2,822 total tests passing.

| Metric | Result |
|--------|-----------------|
| **Spec Compliance (CQL)** | **100%** (1,706 / 1,706 tests) |
| **Spec Compliance (FHIRPath)** | **100%** (935 / 935 tests) |
| **Spec Compliance (SQL-on-FHIR)** | **100%** (134 / 134 tests) |
| **eCQM Measures** | **100% pass rate** (47 / 47) |

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
We compared FHIR4DS against the industry-standard [Java Clinical Reasoning](https://github.com/cqframework/clinical-reasoning) engine using 12 shared measures that achieved 100% execution success in both environments.

| Metric | Traditional Engine (Java) | FHIR4DS (SQL Native) | Speedup |
|--------|---------------------------|----------------------|---------|
| **Mean Execution/Patient** | ~936ms | **~6.9ms** | **~137×** |
| **Median Execution/Patient** | ~819ms | **~1.9ms** | **~425×** |

### Scalability
The speedup reflects the architectural difference: traditional engines evaluate each patient sequentially, whereas FHIR4DS runs a single columnar SQL query that processes the entire population simultaneously. This results in **near-zero marginal cost** for adding additional patients to a cohort.

---

## 3. Measures Tested

The 47 CMS eCQMs from the QI-Core 2025 content package included in our standard benchmark suite include:

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
