# Continuous Integration

FHIR4DS uses GitHub Actions for automated checks. The workflows are split by
cost and purpose so routine `dev` work gets fast feedback while full
conformance and performance timing remain available on `main`, nightly, and
manual runs.

## Branch Behavior

| Workflow | `dev` Push | `main` Push | Pull Request | Nightly | Manual |
|----------|------------|-------------|--------------|---------|--------|
| CI | Yes, except docs-only changes | Yes, except docs-only changes | Yes, except docs-only changes | No | No |
| Website Check | Yes for website/docs changes | No, deploy workflow handles `main` | Yes for website/docs changes | No | No |
| Spec Conformance | No | Yes | No | Yes | Yes |
| DQM Performance Report | No | No | No | Yes | Yes |

## Blocking vs Report-Only

The `CI` workflow has two blocking Python 3.10 gates. Ruff is blocking for the
packages that have been made lint-clean:

```bash
python -m ruff check \
  fhir4ds/cli \
  fhir4ds/dqm \
  fhir4ds/sources \
  benchmarks/runner \
  conformance/scripts
```

The focused pytest gate is also blocking:

```bash
python -m pytest \
  fhir4ds/cli/tests \
  fhir4ds/dqm \
  fhir4ds/sources \
  fhir4ds/cql/tests/unit \
  fhir4ds/viewdef
```

The workflow also has a blocking Python 3.11 compatibility job that runs the
same focused pytest set. Python 3.10 remains the primary CI job because it also
owns Ruff and the project-wide minimum version.

## Conformance

The `Spec Conformance` workflow runs:

```bash
python3 conformance/scripts/run_all.py
```

It runs on pushes to `main`, nightly, and manual dispatch. The workflow uploads
the generated JSON reports from `conformance/reports/`.

## DQM Performance

The `DQM Performance Report` workflow runs:

```bash
python3 conformance/scripts/run_dqm.py
python3 benchmarks/runner/dqm_perf_report.py ...
```

The first command generates `conformance/reports/dqm_report.json`. The second
compares that timing report against the checked-in baseline at
`benchmarks/baselines/dqm_2025.json` and writes:

- `benchmarks/output/dqm-performance-report.json`
- `benchmarks/output/dqm-performance-report.md`

The performance report is non-blocking by default. It is intended to highlight
large regressions, not to fail every run because of hosted-runner noise. The
workflow appends the Markdown report to the job summary and retains report
artifacts for 30 days.

Current report thresholds are:

| Threshold | Value |
|-----------|-------|
| Ratio | `2.0x` baseline |
| Absolute increase | `500 ms` |

A measure is flagged only when both thresholds are exceeded.

### Baseline Lifecycle

The checked-in DQM performance baseline lives at:

```text
benchmarks/baselines/dqm_2025.json
```

Update this baseline only when the timing change is intentional and reviewed.
Good reasons include an accepted optimization, a correctness fix with understood
cost, a benchmark fixture change, or a CI runner environment change that makes
old timings no longer comparable.

To refresh the baseline:

```bash
python3 benchmarks/runner/update_dqm_baseline.py --run
```

To validate an existing report without updating the baseline:

```bash
python3 benchmarks/runner/update_dqm_baseline.py --dry-run
```

The helper refuses to update the baseline unless the expected 47 measure records
are present and all passed. When it writes the refreshed baseline, the generated
comparison report is still calculated against the previous checked-in baseline.
Before committing a new baseline, document why the performance expectation
changed in the commit message.

## Submodules

CI intentionally checks out only the DQM conformance fixture submodule:

```bash
git submodule update --init tests/data/ecqm-content-qicore-2025
```

It does not recursively initialize all submodules, because that would pull large
DuckDB source trees that are not needed for the standard Python CI jobs.

## Local Reproduction

Run the blocking CI pytest gate locally:

```bash
python3 -m ruff check \
  fhir4ds/cli \
  fhir4ds/dqm \
  fhir4ds/sources \
  benchmarks/runner \
  conformance/scripts

python3 -m pytest \
  fhir4ds/cli/tests \
  fhir4ds/dqm \
  fhir4ds/sources \
  fhir4ds/cql/tests/unit \
  fhir4ds/viewdef
```

Generate a local DQM performance report:

```bash
python3 conformance/scripts/run_dqm.py
python3 benchmarks/runner/dqm_perf_report.py \
  --current conformance/reports/dqm_report.json \
  --baseline benchmarks/baselines/dqm_2025.json \
  --output-json benchmarks/output/dqm-performance-report.json \
  --output-md benchmarks/output/dqm-performance-report.md
```
