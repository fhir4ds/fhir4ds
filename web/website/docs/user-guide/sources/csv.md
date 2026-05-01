---
id: csv
title: Using CSV Files
sidebar_label: CSV Files
---

# Using CSV Files

The `CSVSource` adapter lets you use flat CSV files as a FHIR data source. You provide a SQL projection that maps your CSV columns to the fhir4ds schema contract.

## When to Use CSVSource

- Your data is in CSV files and you need to construct FHIR JSON from flat columns.
- You want a quick, one-off analysis without converting CSVs to Parquet first.

If your CSV already has `id`, `resourceType`, `resource`, and `patient_ref` columns, consider using `FileSystemSource` with `format='ndjson'` instead.

## Writing a Projection SQL

The key to using CSVSource is the `projection_sql` parameter — a SQL `SELECT` that maps your CSV columns to the four required schema columns (`id`, `resourceType`, `resource`, `patient_ref`).

For details on the expected format of these columns, see the [Data Sources & Zero-ETL Schema Contract](../data-sources#1-the-resources-view).

Use the `{source}` placeholder in your `FROM` clause. At registration time, it's replaced with `read_csv_auto('<your_file_path>')`.

### Example: Patient CSV

Given a CSV with columns: `patient_id`, `birth_date`, `gender`, `first_name`, `last_name`:

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
                'gender', gender,
                'name', json_array(
                    json_object(
                        'family', last_name,
                        'given', json_array(first_name)
                    )
                )
            ) AS resource,
            patient_id AS patient_ref -- Raw ID, no prefix needed
        FROM {source}
    """
)

con = fhir4ds.create_connection()
fhir4ds.attach(con, source)
```

## Tips for Building Projections

- Use DuckDB's `json_object()` to construct nested FHIR structures.
- Use `json_array()` for array fields like `name` and `given`.
- The `resourceType` column is typically a string literal (e.g., `'Patient'`).
- The `resource` column must be valid JSON — `json_object()` handles this automatically.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Forgetting `{source}` in FROM clause | Use `FROM {source}` — it gets replaced with the CSV scanner. |
| Missing required columns in SELECT | Ensure your projection produces `id`, `resourceType`, `resource`, and `patient_ref`. |
| Wrong resource type | The `resource` column must be JSON, not a plain string. Use `json_object()`. |
| Non-existent CSV column names | Check your CSV headers match the column names in your projection SQL. |
