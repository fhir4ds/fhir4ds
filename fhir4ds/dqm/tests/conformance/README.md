# CQL Measure Conformance Runner

A unified infrastructure for executing eCQM measures against `fhir4ds` and comparing results with expected values from official FHIR test bundles.

## Quick Start

```bash
# Run all configured 2025 measures
python3 -m fhir4ds.dqm.tests.conformance --all

# Run a single measure
python3 -m fhir4ds.dqm.tests.conformance --measure CMS165 --verbose

# Run with custom output directory
python3 -m fhir4ds.dqm.tests.conformance --measure CMS165 --output ./my-results
```

## Command-Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--measure` | `-m` | Measure ID to run (e.g., CMS165) |
| `--all` | `-a` | Run all configured measures in the suite |
| `--suite` | | Content suite: '2025' (default) or '2026' |
| `--output` | `-o` | Output directory |
| `--sql-format` | | SQL formatting style: mozilla (default) or default |
| `--verbose` | `-v` | Print verbose output including generated SQL path |
| `--audit` | | Run with three-tier audit: full → population-only → non-audit |
| `--skip-errors` | | Continue on errors instead of stopping |

## Example: Running CMS165

```bash
python3 -m fhir4ds.dqm.tests.conformance --measure CMS165 --verbose
```

### Expected Output

```
Initializing database...
Loading test data for 1 measures...
  Loaded 425 patients, 425 resources in 0.97s
Loading valuesets...
  Loaded 711 valuesets, 45000 codes in 2.50s

Running 1 measures...

============================================================
Measure: CMS165 - Controlling High Blood Pressure
============================================================
Test cases: 68
  SQL written to: benchmarks/output/cql-py/sql/CMS165.sql

Results:
  Patients: 68
  Total time: 1523.5ms
  - Parse: 125.3ms
  - Translate: 1102.1ms
  - Execute: 296.1ms
  Patients/sec: 45

Accuracy: 95.6% (65/68)

Mismatches (3):
  - patient-abc123: {'Numerator': {'actual': True, 'expected': False}}
  - patient-def456: {'Denominator': {'actual': True, 'expected': False}}

Outputs:
  sql: benchmarks/output/cql-py/sql/CMS165.sql
  csv: benchmarks/output/cql-py/results/CMS165.csv
  stats: benchmarks/output/cql-py/stats/CMS165.json
```

## Architecture

The runner is integrated into the `fhir4ds.dqm` test suite:

```
fhir4ds/dqm/tests/conformance/
├── __init__.py         # Package exports
├── __main__.py         # Entry point for python -m
├── cli.py              # Command-line interface
├── config.py           # Measure configurations and path resolution
├── database.py         # DuckDB setup and data loading
├── runner.py           # CQL execution and timing
├── result_writer.py    # Output file generation
└── loader.py           # FHIR bundle parsing
```

### Data Flow

1.  **Initialization**: Creates DuckDB connection and registers UDFs (C++ or Python fallback).
2.  **Loading**: Parses FHIR bundles from `tests/data/` and loads resources/valuesets.
3.  **Execution**: Parses CQL, translates to population-level SQL, and executes in DuckDB.
4.  **Verification**: Compares results against expected values from `MeasureReport` resources in the bundles.
5.  **Output**: Generates SQL, CSV, and Stats JSON in the `benchmarks/output/` directory.

## Test Data Location

Test data is loaded from the `tests/data/` directory:

```
tests/data/ecqm-content-qicore-2025/
├── input/
│   ├── cql/                          # CQL libraries
│   ├── tests/measure/                # Test cases (Patient bundles)
│   └── vocabulary/valueset/external/  # ValueSet definitions
```

## Troubleshooting

### ModuleNotFoundError

Always run from the project root:
```bash
python3 -m fhir4ds.dqm.tests.conformance --all
```

### FileNotFoundError: CQL file not found

Ensure submodules are initialized:
```bash
git submodule update --init --recursive
```
