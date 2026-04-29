---
id: benchmarking
title: Benchmarking & Accuracy
---

# Benchmarking & Accuracy

FHIR4DS is rigorously tested against the official CMS eCQM test bundles from the [ecqm-content-qicore-2025](https://github.com/cqframework/ecqm-content-qicore-2025) package. These are the same industry-standard test datasets used to certify all conformant clinical reasoning engines.

## 1. Accuracy Results

FHIR4DS achieves near-perfect accuracy across the official CMS quality measure suite.

| Metric | Result |
|--------|-----------------|
| **Measures Tested** | 46 (QI-Core 2025) |
| **Measures at 100% Accuracy** | **42 / 46** |
| **Spec Compliance (CQL)** | 100% (3,044 tests) |
| **Spec Compliance (FHIRPath)** | 100% (935 tests) |
| **Spec Compliance (SQL-on-FHIR)** | 100% (134 tests) |

### Known Upstream Issues
The 4 measures that do not currently achieve 100% accuracy fail due to documented bugs in the official CMS test bundles themselves, rather than implementation errors in FHIR4DS. These measures fail equally in other conformant engines.

| Measure | Issue in Upstream Test Data |
|---------|-----------------------------|
| **CMS135** | Heart Failure — references non-existent practitioner resources |
| **CMS145** | IVF — missing required procedure resources in bundle |
| **CMS157** | Oncology — diagnosis codes don't align with measure valuesets |
| **CMS1017** | Palliative Care — FHIR R4 observation category extension missing |

---

## 2. Performance & Throughput

By leveraging a SQL-native, vectorized architecture, FHIR4DS provides a transformative performance advantage over traditional engines.

### Head-to-Head: FHIR4DS vs. Java Reference Engine
We compared FHIR4DS against the industry-standard [Java Clinical Reasoning](https://github.com/cqframework/clinical-reasoning) engine using 10 shared measures that achieved 100% accuracy in both environments.

| Metric | Traditional Engine (Java) | FHIR4DS (SQL Native) | Speedup |
|--------|---------------------------|----------------------|---------|
| **Mean Execution/Patient** | ~968ms | **~13ms** | **~73×** |
| **Median Execution/Patient** | ~839ms | **~2ms** | **~405×** |

### Scalability
The speedup reflects the architectural difference: traditional engines evaluate each patient sequentially, whereas FHIR4DS runs a single columnar SQL query that processes the entire population simultaneously. This results in **near-zero marginal cost** for adding additional patients to a cohort.

---

## 3. Measures Tested

The 46 CMS eCQMs from the QI-Core 2025 content package included in our standard benchmark suite include:

- **CMS74** — Primary Caries Prevention
- **CMS75** — Children with Dental Decay
- **CMS124** — Cervical Cancer Screening
- **CMS130** — Colorectal Cancer Screening
- **CMS159** — Depression Remission
- **CMS349** — HIV Screening
- ... and 40 additional measures.

---

## 4. Running Benchmarks Locally

To verify these results in your own environment, you can run the benchmark suite directly from the repository:

```bash
# Navigate to the benchmarking directory
cd benchmarks

# Run the full 2025 QI-Core suite
python -m runner --suite 2025 --skip-errors
```
