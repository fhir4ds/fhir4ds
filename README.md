# FHIR4DS

**FHIR for Data Science** - A unified suite of high-performance tools for working with FHIR healthcare data in analytical environments.

## Overview

FHIR4DS provides high-performance tools for querying and transforming FHIR data. Built on DuckDB for efficient analytical processing, it offers native support for FHIRPath expressions, CQL clinical quality measures, and SQL-on-FHIR v2 ViewDefinitions.

## Packages (Unified Namespace)

The project is now organized under the `fhir4ds` namespace for a clean, professional API.

| Feature | Import Path | Description |
|-----------|-------------|-------------|
| **FHIRPath** | `fhir4ds.fhirpath` | Core FHIRPath expression evaluator |
| **FHIRPath (DuckDB)** | `fhir4ds.fhirpath.duckdb` | DuckDB UDFs and C++ extension for FHIRPath |
| **CQL** | `fhir4ds.cql` | CQL parser and SQL translator |
| **CQL (DuckDB)** | `fhir4ds.cql.duckdb` | DuckDB UDFs and translations for CQL |
| **ViewDefinition** | `fhir4ds.viewdef` | SQL-on-FHIR v2 ViewDefinition to SQL generator |
| **DQM** | `fhir4ds.dqm` | Digital Quality Measure orchestrator & audit engine |

### Non-Python Components

- **C++ Extensions**: Located in `extensions/fhirpath` and `extensions/cql`. These provide native high-performance DuckDB extensions.
- **Web Demos**: Located in `web/wasm-demo` and `web/website`.

## Quick Start

### Installation

```bash
pip install fhir4ds-v2

# With optional measure evaluation dependencies (numpy, pandas, etc.)
pip install "fhir4ds-v2[measures]"
```

### Unified Connection

The easiest way to get started is the `create_connection` helper, which returns a DuckDB connection with all FHIRPath and CQL UDFs pre-registered.

```python
import fhir4ds

con = fhir4ds.create_connection()

# Load FHIR data
con.execute("CREATE TABLE resources AS SELECT * FROM 'data/*.parquet'")
```

### FHIRPath Queries

```python
result = con.execute("""
    SELECT
        fhirpath_text(resource, 'Patient.id') AS patient_id,
        fhirpath_text(resource, 'Patient.name.given[0]') AS given_name
    FROM resources
    WHERE resourceType = 'Patient'
""").fetchdf()
```

### CQL Measure Evaluation

```python
result = fhir4ds.evaluate_measure(
    library_path="./CMS165.cql",
    conn=con,
    output_columns={
        "ip": "Initial Population",
        "denom": "Denominator",
        "numer": "Numerator",
    }
)
print(result.df())
```

### SQL-on-FHIR ViewDefinitions

```python
import json

view_definition = {
    "resource": "Patient",
    "select": [{"column": [
        {"path": "id", "name": "patient_id"},
        {"path": "gender", "name": "gender"},
    ]}]
}

sql = fhir4ds.generate_view_sql(json.dumps(view_definition))
patients_flat = con.execute(sql).df()
```

### Standalone FHIRPath

```python
from fhir4ds.fhirpath import evaluate

patient = {
    "resourceType": "Patient",
    "id": "123",
    "name": [{"given": ["John"], "family": "Doe"}]
}

result = evaluate(patient, "Patient.name.given")
# result: ["John"]
```

## Test Coverage & Compliance

The unified engine is rigorously tested against official specifications.

| Component | Unit Tests | Official Compliance |
|-----------|------------|---------------------|
| `fhir4ds.fhirpath` | ✅ Passing | 934/935 FHIRPath R4 (99.9%) |
| `fhir4ds.cql` | ✅ Passing | 3044/3044 CQL Parsing (100%) |
| `fhir4ds.viewdef` | ✅ Passing | 384/384 ViewDefinition v2 (100%) |
| `fhir4ds.dqm` | ✅ Passing | N/A |

## Architecture

The project follows a **Feature-First** hierarchy:

- `fhir4ds/`: Unified Python package root.
  - `fhirpath/`: Core FHIRPath engine.
    - `duckdb/`: DuckDB-specific FHIRPath integration.
  - `cql/`: Core CQL-to-SQL translator.
    - `duckdb/`: DuckDB-specific CQL integration.
  - `viewdef/`: SQL-on-FHIR v2 implementation.
  - `dqm/`: Digital Quality Measure orchestration.
- `extensions/`: High-performance C++ source for DuckDB extensions.
- `web/`: Documentation website and interactive WASM demos.

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/joelmontavon/fhir4ds-v2.git
cd fhir4ds

# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all Python tests
pytest fhir4ds/

# Run specific subpackage tests
pytest fhir4ds/fhirpath/tests/
pytest fhir4ds/cql/tests/

# Run official compliance tests
pytest fhir4ds/cql/tests/official/test_cql_compliance.py
python3 scripts/run_compliance.py --test-dir fhir4ds/fhirpath/tests/compliance/r4
```

## Benchmarking

Performance benchmarking tools and datasets are located in the `benchmarking/` directory. See [benchmarking/AGENTS.md](./benchmarking/AGENTS.md) for details.

## License

This project is dual-licensed:

1.  **Open Source:** GNU Affero General Public License v3 (AGPL-3.0). See [LICENSE](LICENSE) for details.
2.  **Commercial:** A proprietary license for enterprise use, embedding in closed-source products, and high-performance C++ extensions.

For commercial licensing inquiries, please contact **fhir4ds@gmail.com**.
