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

## Zero-ETL Connection

The fastest way to get started is to "attach" FHIR4DS to your existing data. Unlike traditional tools, you don't need to load data into a database first.

```python
import fhir4ds
from fhir4ds.sources import FileSystemSource

# Create a connection and mount local NDJSON or Parquet files instantly
con = fhir4ds.create_connection(
    source=FileSystemSource("data/**/*.ndjson")
)

# Your data is now available as the 'resources' view
```

## FHIRPath Queries

Run high-performance FHIRPath queries directly against your files:

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

Evaluate clinical logic (like QI-Core quality measures) in a single step:

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

Flatten complex FHIR structures into standard tabular data:

```python
# Define a ViewDefinition
view_definition = {
    "resource": "Patient",
    "select": [{"column": [
        {"path": "id", "name": "patient_id"},
        {"path": "gender", "name": "gender"},
    ]}]
}

# Generate and execute SQL
sql = fhir4ds.generate_view_sql(view_definition)
patients_flat = con.execute(sql).df()
```
