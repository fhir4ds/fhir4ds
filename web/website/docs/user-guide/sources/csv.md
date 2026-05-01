---
id: csv
title: Tabular FHIR (CSV)
sidebar_label: CSV
---

# Tabular FHIR (CSV)

The `CSVSource` is designed for scenarios where FHIR data has been exported into flattened CSV files or simple spreadsheets.

## Usage

```python
from fhir4ds.sources import CSVSource

source = CSVSource(
    "exports/measure_results.csv",
    id_col="uuid",
    type_col="resource_type",
    resource_col="full_json",
    patient_col="patient_key"
)

fhir4ds.attach(con, source)
```

## Transformation Strategy

This adapter is often used in "Hybrid" environments where the core resource data (JSON) is kept in one column, while keys used for indexing and partitioning (like `resourceType` and `patient_id`) are kept as standard CSV columns for performance.
