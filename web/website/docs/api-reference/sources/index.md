---
id: sources
title: fhir4ds.sources API Reference
sidebar_label: sources
---

# fhir4ds.sources

The `sources` module provides **Zero-ETL** adapters that mount external data as the standard `resources` view.

## 1. SourceAdapter Protocol

All adapters implement the `SourceAdapter` protocol.

### `register`
`register(con: duckdb.DuckDBPyConnection) -> None`
Creates the `resources` view and performs schema validation.

### `unregister`
`unregister(con: duckdb.DuckDBPyConnection) -> None`
Drops the view and cleans up connections.

---

## 2. Adapters

### `FileSystemSource`
`FileSystemSource(path, *, format=None, credentials=None)`

Connects to local files or cloud storage using DuckDB's native file scanners.

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `str` | File path or glob pattern (e.g. `s3://bucket/*.parquet`). |
| `format` | `str` | `ndjson`, `parquet`, or `iceberg`. Auto-detected if None. |
| `credentials` | `CloudCredentials` | Optional credentials for cloud access. |

---

### `PostgresSource`
`PostgresSource(connection_string, table_mapping)`

Mounts FHIR resources stored in a remote PostgreSQL database.

---

### `CSVSource`
`CSVSource(path, *, id_col="id", type_col="resourceType", resource_col="resource", patient_col="patient_id")`

Maps tabular CSV data into the virtual `resources` schema.

---

### `ExistingTableSource`
`ExistingTableSource(table_name)`

Wraps an existing table or view already present in the DuckDB connection. Useful for legacy ETL pipelines.

---

## 3. Helpers

### `CloudCredentials`
`CloudCredentials(provider, **kwargs)`

Standardized container for S3/GCS/Azure access keys and tokens.
