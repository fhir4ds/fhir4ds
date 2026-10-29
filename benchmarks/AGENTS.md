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

## Baseline refresh (2026-10-24, v0.0.18)

`baselines/dqm_2025.json` was refreshed from the v0.0.18 tree (branch
`feat/cleanroom-redo-20261014` @ `6cdf8dc0`), 47/47 measures at 100% accuracy,
total 85.0s. The previous baseline (May 2025) read 60.9s; the 1.27x growth is
intentional correctness-surface accumulation (CMS2-class SQL guards), verified
identical at S24 (`fb3e65fe`) and HEAD — the S25-S32/0.0.18 campaign itself is
performance-neutral (0.98x on matched /tmp worktrees; the LRU translation cache
offsets added surfaces).

Measurement doctrine: single-machine WSL runs differ by disk — /mnt/d (drvfs)
reads ~12% slower than /tmp worktrees. This baseline was captured on /mnt/d
(the normal development configuration); compare like-for-like.

## Measure-scaling benchmark (2026-10-29)

`benchmarks/scaling/` measures eCQM execution time as the patient corpus grows:
`run_measures.py` (rungs 100/1,000/5,000 Synthea patients; `--memory-limit`,
`--rss-abort-mb`, `--profile`), `analyze_profiles.py` (structural score +
operator attribution), `make_report.py` -> `SCALING.md`.

Durable findings and gotchas:
- Amplification is rung-invariant: each retrieve CTE re-reads the whole
  `resources` table, so rows scanned ~= scan sites x corpus (CMS130 42x, CMS2
  18x, CMS68 7x at every rung). Exec cost is scan-dominated (64-99.5% of
  exclusive operator time), not dedup (0.2-13%).
- Static SQL size/counts rank complexity correctly but understate magnitude;
  `rows evaluated` (scan sites x cohort type counts) is the better static
  predictor, and per-row predicate weight only shows up in the profile.
- Rung 5,000 needs > 33 GB. At `memory_limit=32GB` DuckDB spills (peak RSS
  33.8 GB, CMS130 +17% vs 48 GB); at 48 GB there is no spill (peak RSS 43.9 GB).
- An in-memory DuckDB database MUST set `temp_directory` or exceeding
  `memory_limit` OOMs instead of spilling.
- `EXPLAIN ANALYZE` with `SET enable_profiling='json'` returns the operator
  profile as the second result column (no file needed). With parallel
  execution, per-operator timings are summed across worker threads — use
  shares, and `cumulative_rows_scanned` for true row totals.
- Long runs launched from the agent shell must be `setsid nohup` + `exec` in a
  wrapper script; otherwise the shell timeout kills the process group.

Sequencing ruling (Joel, 2026-10-29): after the DuckDB 2.0.0 work (ext-2
bundles from playground) lands, the next fhir4ds work is the ranked
OPTIMIZATION CANDIDATES from `benchmarks/scaling/SCALING.md`; after
implementing them, this benchmark MUST be re-run on BOTH DuckDB 1.5.5 and
2.0.0 and compared against the committed baseline. Do not delete or overwrite
the current baseline artifacts (`benchmarks/scaling/results/`) — they are the
reference point for that dual-version retest.
