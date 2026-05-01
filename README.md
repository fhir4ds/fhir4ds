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
git clone https://github.com/fhir4ds/fhir4ds.git
cd fhir4ds

# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all Python tests
pytest fhir4ds/

# Run specific subpackage tests
pytest fhir4ds/fhirpath/tests/unit/
pytest fhir4ds/dqm/tests/

# Run official spec conformance suites
python3 conformance/scripts/run_all.py
```

### WASM Demo Release Process

The interactive CQL playground at `web/wasm-demo/` embeds a Python wheel served to Pyodide. After any Python source change or version bump, update the WASM demo:

```bash
# 1. Build the Python wheel
hatch build -t wheel

# 2. Copy to public/ and remove the old version
cp dist/fhir4ds_v2-NEW_VERSION-py3-none-any.whl web/wasm-demo/public/
rm web/wasm-demo/public/fhir4ds_v2-OLD_VERSION-py3-none-any.whl

# 3. Build the WASM demo
cd web/wasm-demo && npm run build

# 4. ⚠️ Deploy to website static directory (required — website uses a pre-built snapshot)
cd ..  # back to repo root
rm -rf web/website/static/wasm-app
cp -r web/wasm-demo/dist/. web/website/static/wasm-app/

# 5. Verify — all 11 tests must pass
cd web/wasm-demo && npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts
```

> **Why step 4 matters:** The website's `static/wasm-app/` is a pre-built snapshot served
> by Docusaurus. It is NOT auto-updated when `web/wasm-demo/` is rebuilt. Skipping step 4
> causes the standalone demo to work while the website CQL playground fails with a Pyodide error.
>
> **Why `duckdb` is excluded from Pyodide:** `duckdb` has no pure Python wheel on PyPI.
> The Pyodide worker uses `deps=False` and manually installs only the required pure-Python
> dependencies. Do not add native C extension packages as hard imports in `fhir4ds.cql`
> or any module imported by the WASM worker. See `AGENTS.md` and `web/wasm-demo/AGENTS.md`
> for full details.

## Benchmarks

Performance benchmarking tools and results are located in the `benchmarks/` directory. See [benchmarks/AGENTS.md](./benchmarks/AGENTS.md) for details.

## License

This project is dual-licensed:

1.  **Open Source:** GNU Affero General Public License v3 (AGPL-3.0). See [LICENSE](LICENSE) for details.
2.  **Commercial:** A proprietary license for enterprise use, embedding in closed-source products, and high-performance C++ extensions.

For commercial licensing inquiries, please contact **fhir4ds@gmail.com**.
