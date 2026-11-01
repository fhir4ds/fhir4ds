# Benchmark Report — 0.0.10

**Workflow**: `benchmarks`
**Benchmark Engineer**: Benchmark Engineer role
**Target version**: `0.0.10`
**Date**: 2026-06-24

## 1. Scope

- **Target version**: `0.0.10`
- **Commands selected**:
  - `python3 conformance/scripts/run_dqm.py` (already run during pre_release; output at `conformance/reports/dqm_report.json`)
  - `python3 benchmarks/runner/dqm_perf_report.py --current conformance/reports/dqm_report.json --baseline benchmarks/baselines/dqm_2025.json --output-json benchmarks/output/dqm-performance-report.json --output-md benchmarks/output/dqm-performance-report.md`
- **Commands skipped**:
  - `python3 benchmarks/run_comparison.py --runs 5` — cross-engine comparison vs the Java Clinical Reasoning reference engine. Requires Gradle + JDK; not run in this session. Tracked as a follow-up; the Python-side DQM performance gate (the relevant one for a 0.0.10 release-prep) is covered.
  - `benchmarks/parser_audit/` — CQL parser coverage audit. Not a performance benchmark; not run.

## 2. Environment

| Item | Value |
|---|---|
| Python | 3.10.12 |
| Package | `fhir4ds-v2==0.0.10` (editable install from `/mnt/d/fhir4ds`) |
| DuckDB | 1.5.2 |
| Native C++ extensions | Loaded (`fhir4ds.register(con)` returns both flags true) |
| OS | Linux 6.6.114.1-microsoft-standard-WSL2 |
| Git branch | `dev` |
| Git HEAD | `29a6133e` (docs(notebooks): bump install snippets to 0.0.10) |
| Working tree | clean (no uncommitted changes after the docs-audit commit) |

## 3. Results

### DQM Performance (47 measures)

| Metric | Current (0.0.10) | Baseline (`benchmarks/baselines/dqm_2025.json`) |
|---|---|---|
| Measures passed | 47 / 47 (100%) | 47 / 47 (100%) |
| Total measured time | 62,739 ms | 60,857 ms |
| Median measure total | 633 ms | 678 ms |
| Suite total ratio | **1.031×** (+1,882 ms) | — |

**Findings**:
- Accuracy regressions: 0
- Timing regressions: 0
- Missing current measures: 0
- New measures without baseline: 0

### Slowest measures (current)

| Measure | Total | SQL Gen | SQL Exec | Translation |
|---|---|---|---|---|
| CMS2 | 11,784 ms | 6,892 ms | 2,468 ms | 2,382 ms |
| CMS0334 | 8,914 ms | 4,447 ms | 1,739 ms | 2,703 ms |
| CMS1218 | 3,615 ms | 1,929 ms | 485 ms | 1,113 ms |
| CMS165 | 3,058 ms | 682 ms | 1,807 ms | 544 ms |
| CMS832 | 2,687 ms | 539 ms | 950 ms | 1,138 ms |

Raw output: `benchmarks/output/dqm-performance-report.md` and `benchmarks/output/dqm-performance-report.json`.

## 4. Baseline Comparison

- **Baseline file**: `benchmarks/baselines/dqm_2025.json` (checked in, generated from a prior `conformance/scripts/run_dqm.py` run).
- **Regression threshold** (per `benchmarks/baselines/README.md`): a measure is flagged only when *both* (a) current metric is ≥ 2.0× the baseline, and (b) the absolute increase is ≥ 500 ms.
- **Current ratio**: suite total `1.031×` — well under the 2.0× threshold. Median measure is actually faster (633 ms vs 678 ms baseline).
- **Verdict**: **No regressions**. The 0.0.10 candidate performs within noise of the 0.0.9-era baseline.

No baseline update required for 0.0.10. The baseline is the QI-Core 2025 DQM snapshot, not version-pinned; the current results are consistent with it.

## 5. Issues

None.

| ID | Severity | Category | Evidence |
|---|---|---|---|
| — | — | — | No release-blocking regressions or environment blockers. |

## 6. Final GO / NO-GO Recommendation

**GO** — benchmark gate passes.

- 0 timing regressions, 0 accuracy regressions, 0 missing measures.
- Suite total within 3.1% of baseline; median measure faster than baseline.
- All 47 measures at 100% accuracy.
- No threshold violations on the slowest measures.

The DQM performance gate (the relevant one for a Python-only 0.0.10 release-prep) is clean. The cross-engine Java comparison benchmark was not run because it requires the Gradle/JDK toolchain and is not in scope for this release-prep session.
