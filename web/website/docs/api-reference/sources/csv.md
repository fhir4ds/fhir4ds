---
id: sources-csv
title: CSVSource
sidebar_label: CSVSource
---

# CSVSource

`fhir4ds.sources.CSVSource` — SourceAdapter for FHIR resources stored in CSV files, where the user defines a SQL projection mapping their column layout to the fhir4ds schema.

## Class Signature

```python
CSVSource(path: str, projection_sql: str)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `str` | Path to the CSV file or glob pattern. |
| `projection_sql` | `str` | A SQL `SELECT` statement projecting CSV columns to the fhir4ds schema. Must use the `{source}` placeholder in the `FROM` clause. |

**Raises:** `SchemaValidationError` — if the projection does not produce the required columns (`id`, `resourceType`, `resource`, `patient_ref`) with the required types.

---

## The `{source}` Placeholder

The `projection_sql` must contain `{source}` in its `FROM` clause. At registration time, this placeholder is replaced with `read_csv_auto('<path>')`, which is DuckDB's CSV scanner.

```sql
-- Your projection_sql:
SELECT ... FROM {source}

-- Becomes:
SELECT ... FROM read_csv_auto('/data/patients.csv')
```

This lets you write portable projection SQL that doesn't depend on the file path.

---

## Methods

### `register(con)`

1. Substitutes `{source}` with `read_csv_auto('<path>')`.
2. Creates `CREATE OR REPLACE VIEW resources AS <projection>`.
3. Calls `validate_schema()`.

**Raises:** `SchemaValidationError` if the projection doesn't expose the required columns, or if the view cannot be created (e.g., projection references non-existent CSV columns).

### `unregister(con)`

Drops the `resources` view. Safe to call even if `register()` was never called.

### `supports_incremental()`

Returns `False`. CSVSource does not support incremental delta tracking.

---

## Example

```python
import fhir4ds
from fhir4ds.sources import CSVSource

source = CSVSource(
    path='/data/patients.csv',
    projection_sql="""
        SELECT
            patient_id AS id,
            'Patient'  AS resourceType,
            json_object(
                'resourceType', 'Patient',
                'id', patient_id,
                'birthDate', birth_date,
                'gender', gender
            ) AS resource,
            patient_id AS patient_ref
        FROM {source}
    """
)

con = fhir4ds.create_connection()
fhir4ds.attach(con, source)
```

---

## Constructing FHIR JSON from CSV Columns

Use DuckDB's `json_object()` function to build the FHIR resource JSON from flat CSV columns:

```sql
json_object(
    'resourceType', 'Patient',
    'id', patient_id,
    'birthDate', birth_date,
    'gender', gender,
    'name', json_array(
        json_object('family', last_name, 'given', json_array(first_name))
    )
) AS resource
```

The projection must produce a column named `resource` with a type castable to `JSON`.

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Forgetting `{source}` in FROM clause | `SchemaValidationError` or DuckDB parse error | Use `FROM {source}` in your projection SQL |
| Missing required columns | `SchemaValidationError: required column 'patient_ref' is missing` | Ensure your SELECT produces all four columns: `id`, `resourceType`, `resource`, `patient_ref` |
| Wrong column types | `SchemaValidationError: column 'resource' has type 'VARCHAR' but 'JSON' is required` | Wrap your resource construction in `json_object()` or cast with `::JSON` |
| Referencing non-existent CSV columns | `SchemaValidationError: failed to create the 'resources' view` | Check your CSV headers match the column names in your projection |
