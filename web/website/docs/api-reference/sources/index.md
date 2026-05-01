---
id: sources
title: fhir4ds.sources
sidebar_label: sources
---

# fhir4ds.sources

The `sources` module provides **Zero-ETL** source adapters that mount external data as the standard `resources` view in DuckDB, enabling CQL measures, FHIRPath queries, and ViewDefinitions to run directly against external data without copying it.

## Top-Level API

### `fhir4ds.attach(con, adapter)`

Registers a source adapter against an existing DuckDB connection.

```python
fhir4ds.attach(con, adapter)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `con` | `duckdb.DuckDBPyConnection` | An active DuckDB connection. |
| `adapter` | `SourceAdapter` | Any object implementing the `SourceAdapter` protocol. |

**Raises:**
- `SchemaValidationError` — if the adapter's view does not conform to the required schema.
- `TypeError` — if `adapter` does not implement the `SourceAdapter` protocol.

### `fhir4ds.detach(con, adapter)`

Unregisters an adapter, dropping the `resources` view and releasing any external connections.

```python
fhir4ds.detach(con, adapter)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `con` | `duckdb.DuckDBPyConnection` | An active DuckDB connection. |
| `adapter` | `SourceAdapter` | The adapter to unregister. |

### `fhir4ds.create_connection(source=...)`

The `source` parameter accepts any `SourceAdapter`. When provided, the adapter is registered immediately after connection creation:

```python
con = fhir4ds.create_connection(
    source=FileSystemSource('/data/fhir/**/*.parquet')
)
```

---

## SourceAdapter Protocol

All adapters implement the `SourceAdapter` protocol, which requires two methods:

```python
class SourceAdapter(Protocol):
    def register(self, con) -> None: ...
    def unregister(self, con) -> None: ...
```

**`register(con)`** — Creates the `resources` view and validates the schema. Must be idempotent (safe to call multiple times). Must call `validate_schema()` before returning.

**`unregister(con)`** — Drops the `resources` view and releases external connections. Safe to call even if `register()` was never called.

### Schema Contract

The `resources` view must expose exactly these columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `VARCHAR` | FHIR resource logical ID |
| `resourceType` | `VARCHAR` | FHIR resource type (e.g. `"Patient"`) |
| `resource` | `JSON` | Complete FHIR resource as JSON |
| `patient_ref` | `VARCHAR` | Raw logical ID of the Patient this resource belongs to |

---

## SchemaValidationError

```python
class SchemaValidationError(Exception)
```

Raised at registration time when a source adapter's `resources` view does not conform to the required schema. The error message identifies the missing or mistyped column and the adapter class.

---

## validate_schema()

```python
validate_schema(con, adapter_class_name: str) -> None
```

Validates that the `resources` view conforms to the required schema. Every adapter must call this immediately after creating the view.

| Parameter | Type | Description |
|-----------|------|-------------|
| `con` | `duckdb.DuckDBPyConnection` | An active DuckDB connection. |
| `adapter_class_name` | `str` | Name of the calling adapter class (used in error messages). |

**Raises:** `SchemaValidationError` if the view is absent, or any required column is missing or has the wrong type.

---

## quote_identifier()

```python
quote_identifier(name: str) -> str
```

Safely quotes a DuckDB identifier to prevent SQL injection. Escapes internal double-quotes by doubling them, then wraps in double-quotes.

Used internally by `PostgresSource` and `ExistingTableSource` to safely handle user-supplied table and column names.

---

## Built-In Adapters

| Adapter | Purpose | Details |
|---------|---------|---------|
| [`FileSystemSource`](filesystem) | Parquet, NDJSON, Iceberg (local or cloud) | [API Reference →](filesystem) |
| [`PostgresSource`](relational) | FHIR JSON in Postgres columns | [API Reference →](relational) |
| [`ExistingTableSource`](existing) | Wrap pre-loaded DuckDB tables | [API Reference →](existing) |
| [`CSVSource`](csv) | CSV files with user-defined projection | [API Reference →](csv) |

### CloudCredentials

```python
CloudCredentials(provider: str, secret_name: str = None, **kwargs)
```

Encapsulates DuckDB secret configuration for cloud storage access.

| Parameter | Type | Description |
|-----------|------|-------------|
| `provider` | `str` | `'S3'`, `'AZURE'`, or `'GCS'` |
| `secret_name` | `str` | Optional name for the DuckDB secret. Defaults to `fhir4ds_{provider}_secret`. |
| `**kwargs` | | Provider-specific credential fields (see below). |

**Provider-specific fields:**

| Provider | Fields |
|----------|--------|
| S3 | `access_key_id`, `secret_access_key`, `region`, `endpoint_url` |
| Azure | `connection_string`, or `account_name` + `account_key` |
| GCS | `service_account_json` |

**Method:** `configure(con)` — Registers a DuckDB secret for this provider.
