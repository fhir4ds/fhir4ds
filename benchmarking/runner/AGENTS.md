# CQL Measure Benchmarking Runner

A unified benchmarking infrastructure for executing eCQM measures against cql-py and comparing results with expected values.

## Quick Start

```bash
# Run a single measure
python3 -m benchmarking.runner --measure CMS165 --verbose

# Run all configured measures
python3 -m benchmarking.runner --all

# Run with custom output directory
python3 -m benchmarking.runner --measure CMS165 --output ./my-results
```

## Installation

Ensure you have the required dependencies:

```bash
pip install sqlparse
pip install -e ./cql-py  # Install cql-py in development mode
```

## Command-Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--measure` | `-m` | Measure ID to run (e.g., CMS165) |
| `--all` | `-a` | Run all configured measures |
| `--output` | `-o` | Output directory (default: benchmarking/output/cql-py) |
| `--sql-format` | | SQL formatting style: mozilla (default) or default |
| `--compare` | | Compare with reference implementation (cql-execution-validator) |
| `--verbose` | `-v` | Print verbose output including generated SQL path |
| `--audit` | | Run with three-tier audit: full → population-only → non-audit |
| `--skip-errors` | | Continue on errors instead of stopping |

## Example: Running CMS165

CMS165 (Controlling High Blood Pressure) is used as the primary example measure.

### Basic Execution

```bash
python3 -m benchmarking.runner --measure CMS165 --verbose
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
  SQL written to: benchmarking/output/cql-py/sql/CMS165.sql

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
  - patient-ghi789: {'Initial Population': {'actual': False, 'expected': True}}

Outputs:
  sql: benchmarking/output/cql-py/sql/CMS165.sql
  csv: benchmarking/output/cql-py/results/CMS165.csv
  stats: benchmarking/output/cql-py/stats/CMS165.json
```

### Output Files

After running a measure, three output files are generated:

#### 1. SQL File (`output/cql-py/sql/CMS165.sql`)

The generated SQL query for the measure:

```sql
-- Generated SQL for CMS165

WITH _patients AS (
  SELECT DISTINCT patient_ref AS patient_id FROM resources WHERE patient_ref IS NOT NULL
),
_patient_demographics AS (
  SELECT DISTINCT r.patient_ref AS patient_id,
         r.resource,
         CAST(fhirpath_date(r.resource, 'birthDate') AS DATE) AS birth_date
  FROM resources r
  WHERE r.resourceType = 'Patient'
),
"Initial Population" AS (
  SELECT p.patient_id FROM _patients AS p ...
),
...
SELECT
  p.patient_id,
  CASE WHEN "Initial Population".patient_id IS NOT NULL THEN TRUE ELSE FALSE END AS "Initial_Population",
  CASE WHEN "Denominator".patient_id IS NOT NULL THEN TRUE ELSE FALSE END AS "Denominator",
  CASE WHEN "Numerator".patient_id IS NOT NULL THEN TRUE ELSE FALSE END AS "Numerator"
FROM _patients p
LEFT JOIN "Initial Population" ON p.patient_id = "Initial Population".patient_id
LEFT JOIN "Denominator" ON p.patient_id = "Denominator".patient_id
LEFT JOIN "Numerator" ON p.patient_id = "Numerator".patient_id
ORDER BY p.patient_id
```

#### 2. CSV File (`output/cql-py/results/CMS165.csv`)

Per-patient results with expected values:

```csv
patient_id,Initial_Population,Denominator,Numerator,expected_Initial_Population,expected_Denominator,expected_Numerator,match
patient-001,TRUE,TRUE,FALSE,TRUE,TRUE,FALSE,TRUE
patient-002,TRUE,TRUE,TRUE,TRUE,TRUE,TRUE,TRUE
patient-003,TRUE,FALSE,FALSE,TRUE,TRUE,FALSE,FALSE
```

#### 3. Stats File (`output/cql-py/stats/CMS165.json`)

Performance and accuracy metrics:

```json
{
  "measure_id": "CMS165",
  "patient_count": 68,
  "timings_ms": {
    "cql_parse_ms": 125.3,
    "sql_generation_ms": 1102.1,
    "sql_execution_ms": 296.1,
    "total_ms": 1523.5
  },
  "patients_per_second": 45,
  "comparison": {
    "total_patients": 68,
    "matching_patients": 65,
    "accuracy_pct": 95.6
  }
}
```

## Supported Measures

The following measures are pre-configured:

| Measure ID | Name |
|------------|------|
| CMS124 | Cervical Cancer Screening |
| CMS144 | Heart Failure Beta Blocker Therapy |
| CMS165 | Controlling High Blood Pressure |

To add a new measure, edit `config.py` and add a new `MeasureConfig` entry.

## Architecture

```
benchmarking/runner/
├── __init__.py         # Package initialization
├── __main__.py         # Entry point for python -m
├── cli.py              # Command-line interface
├── config.py           # Measure configurations
├── database.py         # DuckDB setup and data loading
├── measure_runner.py   # CQL execution and timing
├── result_writer.py    # Output file generation
├── test_loader.py      # FHIR bundle parsing
└── reference_runner.py # Reference implementation comparison
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    INITIALIZATION                           │
├─────────────────────────────────────────────────────────────┤
│  1. Create DuckDB connection                                │
│  2. Register UDFs (fhirpath, in_valueset, etc.)            │
│  3. Load test patients from FHIR bundles                    │
│  4. Load ValueSets into valueset_codes table               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    PER-MEASURE EXECUTION                    │
├─────────────────────────────────────────────────────────────┤
│  1. Parse CQL library                                       │
│  2. Translate to SQL (with CTEs for each definition)       │
│  3. Execute SQL against pre-loaded data                    │
│  4. Compare results with expected values from MeasureReport │
│  5. Write outputs (CSV, SQL, JSON)                         │
└─────────────────────────────────────────────────────────────┘
```

## Test Data Location

Test data is loaded from the ecqm-content-qicore-2025 submodule:

```
benchmarking/data/ecqm-content-qicore-2025/
├── input/
│   ├── cql/                          # CQL libraries
│   │   ├── CMS165FHIRControllingHighBloodPressure.cql
│   │   ├── FHIRHelpers.cql
│   │   └── QICoreCommon.cql
│   ├── tests/measure/                # Test cases
│   │   └── CMS165FHIRControllingHighBloodPressure/
│   │       ├── tests-patient-001-bundle.json
│   │       ├── tests-patient-002-bundle.json
│   │       └── ...
│   └── vocabulary/valueset/external/  # ValueSet definitions
│       └── valueset-*.json (711 files)
```

## Troubleshooting

### ModuleNotFoundError

```bash
# Run from project root
cd /mnt/d/duckdb-fhirpath

# Or add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### FileNotFoundError: CQL file not found

```bash
# Initialize submodule
git submodule update --init --recursive

# Verify files exist
ls benchmarking/data/ecqm-content-qicore-2025/input/cql/
```

### UDF not found errors

Ensure duckdb-cql-py is properly installed:

```bash
pip install -e ./duckdb-cql-py
pip install -e ./duckdb-fhirpath-py
```

## Extending the Benchmarking Runner

### Adding a New Measure

1. Add the CQL file to the submodule (or reference existing)
2. Edit `config.py`:

```python
MEASURES["CMSNEW"] = MeasureConfig(
    id="CMSNEW",
    name="New Measure Name",
    cql_path=CQL_DIR / "CMSNEWFHIRNewMeasure.cql",
    test_dir=TESTS_DIR / "CMSNEWFHIRNewMeasure",
    include_paths=[CQL_DIR],
    valueset_paths=[VALUESET_DIR],
    population_definitions=[
        "Initial Population",
        "Denominator",
        "Numerator",
    ],
)
```

### Custom Output Processing

The `MeasureResult` dataclass contains all data needed for custom processing:

```python
from benchmarking.runner.measure_runner import run_measure
from benchmarking.runner.database import BenchmarkDatabase
from benchmarking.runner.config import MEASURES
from benchmarking.runner.test_loader import load_test_suite

db = BenchmarkDatabase()
config = MEASURES["CMS165"]
db.load_all_test_data([config])
db.load_all_valuesets(config.valueset_paths)

suite = load_test_suite(config)
result = run_measure(db.conn, config, suite)

# Access results
print(f"SQL: {len(result.sql)} chars")
print(f"Patients: {result.patient_count}")
print(f"Timings: {result.timings}")
print(f"Accuracy: {result.comparison.accuracy_pct}%")
```

## License

Part of the duckdb-fhirpath project.
