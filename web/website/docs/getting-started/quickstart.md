---
id: quickstart
title: Quick Start
---

# Quick Start

## Installation

```bash
# Install the unified FHIR4DS package
pip install fhir4ds-v2
```

## Unified Connection

The easiest way to get started is using the unified `create_connection` helper, which returns a DuckDB connection with all FHIRPath and CQL UDFs pre-registered.

```python
import fhir4ds

# Create a connection with all UDFs registered
con = fhir4ds.create_connection()

# Load FHIR data
con.execute("CREATE TABLE resources AS SELECT * FROM 'data/*.parquet'")
```

## FHIRPath Queries

```python
# Query with native FHIRPath
result = con.execute("""
  SELECT
    fhirpath_text(resource, 'Patient.id') AS patient_id,
    fhirpath_text(resource, 'Patient.name.given[0]') AS given_name
  FROM resources
  WHERE resourceType = 'Patient'
""").fetchdf()
```

## CQL Measure Evaluation

```python
# Evaluate a Clinical Quality Measure using the high-level API
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

## SQL-on-FHIR ViewDefinitions

```python
import json

# Define a ViewDefinition
view_definition = {
    "resource": "Patient",
    "select": [{"column": [
        {"path": "id", "name": "patient_id"},
        {"path": "gender", "name": "gender"},
    ]}]
}

# Generate SQL from a ViewDefinition
sql = fhir4ds.generate_view_sql(json.dumps(view_definition))

# Execute against DuckDB
patients_flat = con.execute(sql).df()
```
