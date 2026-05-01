---
id: sources-relational
title: PostgresSource
sidebar_label: PostgresSource
---

# PostgresSource

`fhir4ds.sources.PostgresSource` — SourceAdapter for FHIR resources stored as JSON columns in a PostgreSQL database.

:::caution Scope Boundary
This adapter requires that source tables **already contain FHIR resource JSON** in a designated column. It does **not** construct FHIR JSON from arbitrary relational schemas — that mapping problem is out of scope for this release.
:::

## Class Signature

```python
PostgresSource(
    connection_string: str,
    table_mappings: list[PostgresTableMapping],
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `connection_string` | `str` | Postgres connection string in libpq format, e.g. `'postgresql://user:pass@host:5432/dbname'`. |
| `table_mappings` | `list[PostgresTableMapping]` | One mapping per source table to include in the `resources` view. Must contain at least one mapping. |

**Raises:**
- `ValueError` — if `table_mappings` is empty.
- `SchemaValidationError` — if the resulting view does not conform to the required schema.

---

## PostgresTableMapping

Defines how a single Postgres table maps to the fhir4ds resources schema.

```python
PostgresTableMapping(
    table_name: str,
    id_column: str,
    resource_type: str,
    resource_column: str,
    patient_ref_column: str,
    schema: str = "public",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `table_name` | `str` | *(required)* | Name of the Postgres table. |
| `id_column` | `str` | *(required)* | Column containing the FHIR resource ID (must be castable to `VARCHAR`). |
| `resource_type` | `str` | *(required)* | Literal FHIR resource type string (e.g. `'Patient'`). Used as a constant — not read from the table. |
| `resource_column` | `str` | *(required)* | Column containing the complete FHIR resource as JSON or JSONB. |
| `patient_ref_column` | `str` | *(required)* | Column containing the patient reference ID (must be castable to `VARCHAR`). |
| `schema` | `str` | `"public"` | Postgres schema name. |

### Security Note

All identifiers (`table_name`, column names, `schema`) are quoted via `quote_identifier()` before interpolation into SQL. The `resource_type` literal is escaped by doubling single quotes. This prevents SQL injection from user-supplied names.

---

## Methods

### `register(con)`

1. Installs and loads the DuckDB `postgres` extension.
2. Attaches to the Postgres database using `ATTACH IF NOT EXISTS` (read-only).
3. Creates a unified `resources` view as a `UNION ALL` of all mapped tables.
4. Calls `validate_schema()`.

The call is fully **idempotent** — safe to call multiple times on the same connection.

**Raises:** `SchemaValidationError` if the resulting view does not conform.

### `unregister(con)`

1. Drops the `resources` view.
2. Detaches the Postgres attachment (`DETACH`).

Safe to call even if `register()` was never called.

### `supports_incremental()`

Returns `True`. PostgresSource supports delta tracking via `updated_at` columns.

### `get_changed_patients(since: datetime) -> list[str]`

Queries `updated_at` columns in all mapped tables to find patients modified since `since`.

**Raises:**
- `RuntimeError` — if called before `register()`.
- `NotImplementedError` — if any mapped table lacks an `updated_at` column.

**Limitations:**
- Only detects inserts and updates. Hard deletes are invisible unless the table uses soft-delete with an `updated_at` timestamp.
- All mapped tables must have an `updated_at` column.

---

## Example

```python
import fhir4ds
from fhir4ds.sources import PostgresSource, PostgresTableMapping

source = PostgresSource(
    connection_string='postgresql://user:pass@localhost:5432/clinical',
    table_mappings=[
        PostgresTableMapping(
            table_name='fhir_patients',
            id_column='patient_id',
            resource_type='Patient',
            resource_column='fhir_json',
            patient_ref_column='patient_id',
        ),
        PostgresTableMapping(
            table_name='fhir_observations',
            id_column='obs_id',
            resource_type='Observation',
            resource_column='fhir_json',
            patient_ref_column='patient_id',
        ),
    ]
)

con = fhir4ds.create_connection()
fhir4ds.attach(con, source)

# Run a CQL measure against live Postgres data
result = fhir4ds.evaluate_measure(
    library_path="./CMS165.cql",
    conn=con,
    output_columns={"ip": "Initial Population"},
)
```

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `ValueError: PostgresSource requires at least one PostgresTableMapping` | Empty `table_mappings` list | Provide at least one `PostgresTableMapping`. |
| `SchemaValidationError: column 'resource' has type 'VARCHAR' but 'JSON' is required` | The mapped `resource_column` is `TEXT`/`VARCHAR` instead of `JSON`/`JSONB` | Ensure the Postgres column stores valid JSON. DuckDB casts it to `JSON` during projection. |
| Connection refused | Postgres not reachable | Verify the connection string, ensure Postgres is running, and check firewall/network rules. |
| `ATTACH ... already exists` | Adapter attached twice without detaching | `register()` uses `ATTACH IF NOT EXISTS`, so this should not occur. If it does, call `unregister()` first. |
