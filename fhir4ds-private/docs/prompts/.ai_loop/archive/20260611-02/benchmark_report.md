# Benchmark Report - Release 0.0.9

## 1. Scope

- Target version: `0.0.9`.
- Selected benchmark command:
  `python3 benchmarks/runner/dqm_perf_report.py --current conformance/reports/dqm_report.json --baseline benchmarks/baselines/dqm_2025.json --output-json .temp/release/dqm-performance-report.json --output-md .temp/release/dqm-performance-report.md --fail-on-regression`.
- Supporting validation command:
  `python3 -m pytest benchmarks/runner/tests -q --tb=short`.
- Skipped commands: full cross-engine `benchmarks/run_comparison.py` was not
  selected for this release gate because the repository-maintained DQM baseline
  comparison is the documented release sentinel for `benchmarks/baselines/dqm_2025.json`.

## 2. Environment

- Python: `3.10.12`.
- Platform: Linux WSL2 (`Linux-6.6.114.1-microsoft-standard-WSL2-x86_64`).
- DuckDB: `1.5.2`.
- Package version: `fhir4ds 0.0.9`.
- Native extension status: `{'fhirpath_cpp': True, 'cql_cpp': True}`.
- Scoped change summary: 29 files changed, 106 insertions, 37 deletions across
  release-prep surfaces.

## 3. Results

DQM performance comparison:

```text
Measures passed: 47/47 current, 47/47 baseline
Total measured time: 64,058 ms current, 60,857 ms baseline
Median measure total: 678 ms current, 678 ms baseline
Suite total ratio: 1.053x (+3,201 ms)
Accuracy regressions: 0
Timing regressions: 0
Missing current measures: 0
New measures without baseline: 0
```

Slowest current measures:

| Measure | Total | SQL Gen | SQL Exec | Translation |
| --- | ---: | ---: | ---: | ---: |
| CMS2 | 11,688 ms | 6,819 ms | 2,335 ms | 2,501 ms |
| CMS0334 | 9,304 ms | 4,623 ms | 1,822 ms | 2,836 ms |
| CMS1218 | 3,533 ms | 1,916 ms | 439 ms | 1,096 ms |
| CMS165 | 3,036 ms | 701 ms | 1,756 ms | 552 ms |
| CMS832 | 2,763 ms | 764 ms | 949 ms | 995 ms |

Raw/generated benchmark outputs:

- `.temp/release/dqm-performance-report.json`
- `.temp/release/dqm-performance-report.md`

Benchmark helper tests:

```text
benchmarks/runner/tests/test_update_dqm_baseline.py ... [100%]
3 passed
```

## 4. Baseline Comparison

- Previous baseline: `benchmarks/baselines/dqm_2025.json`.
- Current report: `conformance/reports/dqm_report.json` from the 0.0.9
  pre-release conformance run.
- Regression threshold: ratio `>= 2.0x` and absolute increase `>= 500 ms`.
- Verdict: PASS. The suite total is `1.053x` baseline with zero per-measure
  timing regressions and zero accuracy regressions.

## 5. Issues

No benchmark release blockers were found.

## 6. Final GO / NO-GO Recommendation

**GO** for the benchmark gate. The current 0.0.9 candidate remains within the
checked-in DQM performance baseline thresholds and preserves 47/47 DQM
accuracy.
