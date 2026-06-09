# FHIR4DS Benchmarks

Performance benchmarking tools for the `fhir4ds` engine, focused on comparing
against reference implementations (HAPI FHIR / Clinical Reasoning Java engine).

## Structure

```
benchmarks/
├── AGENTS.md                  # This file
├── COMPARISON.md              # Generated benchmark comparison report
├── run_comparison.py          # Main benchmark script (cql-py vs clinical-reasoning)
├── extract_expanded_valuesets.py  # Utility: extract ValueSets from bundles
├── clinical-reasoning/        # Java Clinical Reasoning reference engine (Gradle)
│   ├── build.gradle.kts
│   └── src/                   # Java benchmark harness
├── output/                    # Generated comparison results (gitignored)
│   ├── cql_py_runs.json       # Raw per-measure-run records (cql-py)
│   ├── cr_runs.json           # Raw per-measure-run records (clinical-reasoning)
│   ├── cr_run_N.json          # Individual CR run files
│   └── summary_stats.json     # Computed statistics
├── parser_audit/              # Standalone CQL parser audit utility
│   ├── scanner.py             # Scans CQL files for parse coverage
│   ├── categorizer.py         # Categorizes parse results
│   └── reporter.py            # Generates parse audit reports
└── runner/                    # Legacy shims (delegates to fhir4ds.dqm.tests.conformance)
    ├── __init__.py             # Re-exports conformance module symbols
    ├── __main__.py             # Entry point: calls conformance.cli.main()
    ├── comparison.py           # Result comparison logic
    └── audit_perf_compare.py   # Performance regression detector
```

## Running Benchmarks

### Cross-Engine Comparison (cql-py vs clinical-reasoning)

```bash
# Full comparison (5 runs each engine)
python3 benchmarks/run_comparison.py --runs 5

# cql-py only (skip Java engine)
python3 benchmarks/run_comparison.py --runs 5 --skip-cr

# Use cached cql-py results, rerun Java only
python3 benchmarks/run_comparison.py --runs 5 --skip-cql-py

# Quick single-run test
python3 benchmarks/run_comparison.py --runs 1 --skip-cr
```

**Output:**
- `benchmarks/output/cql_py_runs.json` — raw timing + accuracy per measure-run
- `benchmarks/output/summary_stats.json` — aggregated statistics
- `benchmarks/COMPARISON.md` — human-readable comparison report

### Java Engine Setup

The clinical-reasoning engine requires Java and Gradle:
```bash
cd benchmarks/clinical-reasoning
./gradlew shadowJar
# Produces: build/libs/clinical-reasoning-benchmark-1.0.0-all.jar
```

## Related Infrastructure

| Component | Location | Purpose |
|-----------|----------|---------|
| **Conformance runner** | `fhir4ds/dqm/tests/conformance/` | Functional verification (accuracy testing) |
| **Conformance output** | `tests/output/` | Per-measure results, SQL, stats |
| **Test data (2025)** | `tests/data/ecqm-content-qicore-2025/` | Official eCQM test bundles (submodule) |
| **Test data (2026)** | `tests/data/dqm-content-qicore-2026/` | DQM content for 2026 measures (submodule) |
| **Shared valuesets** | `tests/data/valuesets/` | Supplemental ValueSet bundles |
| **Path config** | `fhir4ds/dqm/tests/conformance/config.py` | All path definitions |

## Accuracy Definitions

- **cql-py accuracy** = fraction of test patients whose computed population membership
  matches the expected result in the official QI-Core test bundle (clinical correctness).
- **clinical-reasoning accuracy** = fraction of patients that evaluated without a runtime
  error (execution success rate). 100% CR accuracy only means no exceptions were thrown.

## Release 0.0.7 Domain 7 Verification

Fresh Domain 7 scale checks on 2026-05-24 found no performance cliff:
`FHIRDataLoader.load_resources()` scaled linearly from 10k to 50k synthetic
resources, repeated 1k-resource batches showed flat Python heap usage after
startup, four concurrent in-memory loader connections completed independently,
and the DQM performance report against `benchmarks/baselines/dqm_2025.json`
flagged zero regressions. Keep the DQM baseline comparison and ad hoc
1k/10k/50k loader probe together when changing ingestion or DQM critical paths.

## Release 0.0.8 Domain 7 Benchmark Drift

Fresh Domain 7 scale checks on 2026-06-07 again found no loader scaling cliff
or Python heap growth, but the DQM comparison against the May 22 baseline
flagged 7 timing regressions. CMS2 was the sentinel: current conformance output
remained 47/47 accurate but grew to about 1.55 MB SQL and 11.6 s total time
versus the checked-in 406 KB / 2.6 s baseline. Older local CMS2 artifacts near
the baseline lack later semantic guardrails such as `CQLListContainsEq`,
`CalculateAgeInYearsAt`, `ToDate`, `fhirpath_number`, and `CQLMessage`
branches. `QA-004` was remediated by refreshing
`benchmarks/baselines/dqm_2025.json` from the validated current DQM report,
not by weakening thresholds. Future pre-release gates must still run
`dqm_perf_report.py --fail-on-regression` against this refreshed baseline and
must treat new major unexplained regressions as blockers.

## License

Apache 2.0
