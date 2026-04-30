---
id: relational
title: Connecting to PostgreSQL
sidebar_label: PostgreSQL
---

# Connecting to PostgreSQL

The `PostgresSource` adapter lets you evaluate clinical logic against FHIR data stored in a PostgreSQL database — without copying data out of Postgres.

:::caution Scope Boundary
This adapter requires that your Postgres tables **already contain FHIR resource JSON in a column** (JSON or JSONB). It does not construct FHIR JSON from arbitrary relational column schemas. If your data is in a normalized relational schema, you will need to build the FHIR JSON before using this adapter.
:::

## Prerequisites

Your Postgres tables must conform to the [Standard FHIR4DS Schema Contract](../data-sources#1-the-resources-view), specifically:
- A column containing the **FHIR resource ID** (castable to VARCHAR).
- A column containing the **complete FHIR resource as JSON/JSONB**.
- A column containing the **raw Patient ID** (castable to VARCHAR, no prefixes).

## Step-by-Step

### 1. Define Table Mappings

Each Postgres table needs a `PostgresTableMapping` that tells fhir4ds which columns correspond to the schema contract:

```python
from fhir4ds.sources import PostgresTableMapping

patient_mapping = PostgresTableMapping(
    table_name='fhir_patients',
    id_column='patient_id',
    resource_type='Patient',
    resource_column='fhir_json',
    patient_ref_column='patient_id',
)

obs_mapping = PostgresTableMapping(
    table_name='fhir_observations',
    id_column='obs_id',
    resource_type='Observation',
    resource_column='fhir_json',
    patient_ref_column='patient_id',
)
```

### 2. Create the Source and Attach

```python
import fhir4ds
from fhir4ds.sources import PostgresSource

source = PostgresSource(
    connection_string='postgresql://user:pass@localhost:5432/clinical',
    table_mappings=[patient_mapping, obs_mapping],
)

con = fhir4ds.create_connection()
fhir4ds.attach(con, source)
```

### 3. Run a Measure

```python
result = fhir4ds.evaluate_measure(
    library_path="./CMS165.cql",
    conn=con,
    output_columns={"ip": "Initial Population"},
)
print(result.df())
```

## How It Works

When you attach a `PostgresSource`:
1. DuckDB's `postgres` extension is installed and loaded.
2. The Postgres database is attached as a read-only connection.
3. A unified `resources` view is created as a `UNION ALL` of all mapped tables, with columns cast to the required types.
4. Schema validation runs immediately.

Queries against `resources` are pushed down to Postgres — DuckDB fetches only the data needed.

## Idempotency

`register()` is fully idempotent:
- Uses `ATTACH IF NOT EXISTS` for the Postgres connection.
- Uses `CREATE OR REPLACE VIEW` for the resources view.

## Cleanup

`unregister()` drops the `resources` view and detaches the Postgres connection.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Verify connection string, ensure Postgres is running, check firewall rules. |
| `SchemaValidationError: column 'resource' has type 'VARCHAR'` | Ensure the Postgres column stores JSON/JSONB. |
| `ValueError: requires at least one PostgresTableMapping` | Provide at least one mapping. |
| Duplicate attachment | `register()` handles this via `ATTACH IF NOT EXISTS`. |