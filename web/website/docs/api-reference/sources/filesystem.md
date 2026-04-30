---
id: sources-filesystem
title: FileSystemSource
sidebar_label: FileSystemSource
---

# FileSystemSource

`fhir4ds.sources.FileSystemSource` — SourceAdapter for FHIR resources stored as Parquet, NDJSON, or Iceberg files on local disk or cloud object storage (S3, Azure Blob, GCS).

## Class Signature

```python
FileSystemSource(
    path_pattern: str,
    format: str = "parquet",
    credentials: CloudCredentials | None = None,
    hive_partitioning: bool = False,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path_pattern` | `str` | *(required)* | Glob pattern or directory path pointing to source files. |
| `format` | `str` | `"parquet"` | File format: `"parquet"`, `"ndjson"`, `"json"`, or `"iceberg"`. |
| `credentials` | `CloudCredentials` | `None` | Cloud storage credentials. If `None` and path is a cloud URI, a `UserWarning` is emitted. |
| `hive_partitioning` | `bool` | `False` | Enable Hive partition pruning. Recommended for large datasets partitioned by `resourceType` or date. |

**Raises:**
- `ValueError` — if `format` is not one of the supported values.
- `SchemaValidationError` — if the mounted files do not expose the required columns with the required types.

### Source File Schema

Source files **must** already contain the four required columns: `id`, `resourceType`, `resource`, `patient_ref`. The adapter casts them to the correct DuckDB types during view creation.

---

## CloudCredentials

```python
CloudCredentials(
    provider: str,
    secret_name: str | None = None,
    **kwargs,
)
```

Encapsulates DuckDB secret configuration for cloud storage.

| Provider | Fields |
|----------|--------|
| **S3** | `access_key_id`, `secret_access_key`, `region`, `endpoint_url` |
| **Azure** | `connection_string`, or `account_name` + `account_key` |
| **GCS** | `service_account_json` |

### Cloud URI Warning

When `path_pattern` starts with a cloud prefix (`s3://`, `az://`, `abfs://`, `gs://`, `gcs://`) and no `credentials` are provided, `FileSystemSource` emits a `UserWarning`:

> *FileSystemSource path 's3://...' appears to be a cloud URI but no credentials were provided. DuckDB secrets must be configured externally before calling register().*

Pass a `CloudCredentials` instance to suppress this warning.

---

## Methods

### `register(con)`

Mounts the file source as the `resources` view:
1. Configures cloud credentials (if provided).
2. Builds the DuckDB scan expression (`read_parquet()`, `read_json_auto()`, or `iceberg_scan()`).
3. Creates `CREATE OR REPLACE VIEW resources` with explicit type casts.
4. Calls `validate_schema()`.

**Raises:** `SchemaValidationError` if the files do not expose the required columns.

### `unregister(con)`

Drops the `resources` view. Safe to call even if `register()` was never called.

### `supports_incremental()`

Returns `True` for Parquet, NDJSON, and JSON formats. Returns `False` for Iceberg (no file-mtime-based delta tracking).

### `get_changed_patients(since: datetime) -> list[str]`

Returns patient IDs whose source files have been modified since `since` by scanning file modification timestamps.

**Raises:**
- `NotImplementedError` — for Iceberg format.
- `RuntimeError` — if called before `register()`.

**Limitations:**
- File mtime is not a reliable proxy for patient-level changes.
- Deletions within a file are not detectable.
- Cloud storage mtime may have lower resolution than local filesystem.

---

## Examples

### Local Parquet

```python
import fhir4ds
from fhir4ds.sources import FileSystemSource

source = FileSystemSource('/data/fhir/**/*.parquet')
con = fhir4ds.create_connection(source=source)

# The 'resources' view is now available
result = con.execute("SELECT COUNT(*) FROM resources").fetchone()
```

### Local NDJSON

```python
source = FileSystemSource('/data/fhir/ndjson/', format='ndjson')
fhir4ds.attach(con, source)
```

### S3 Parquet with Credentials

```python
from fhir4ds.sources import FileSystemSource, CloudCredentials

creds = CloudCredentials(
    provider="S3",
    access_key_id="AKIAIOSFODNN7EXAMPLE",
    secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    region="us-east-1",
)

source = FileSystemSource(
    "s3://my-bucket/fhir/**/*.parquet",
    credentials=creds,
    hive_partitioning=True,
)
fhir4ds.attach(con, source)
```

### Hive-Partitioned Parquet

```python
# Data partitioned as: /data/fhir/resourceType=Patient/*.parquet
source = FileSystemSource(
    '/data/fhir/**/*.parquet',
    hive_partitioning=True,
)
fhir4ds.attach(con, source)

# DuckDB can now prune partitions — queries filtering on resourceType are much faster
```

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `SchemaValidationError: required column 'resource' is missing` | Source files don't have a `resource` column | Ensure your Parquet/NDJSON files include all four required columns |
| `SchemaValidationError: column 'resource' has type 'VARCHAR' but 'JSON' is required` | The `resource` column is a string, not JSON | The adapter casts automatically — this usually indicates a deeper schema issue |
| `UserWarning: ... cloud URI but no credentials` | Using `s3://` path without `CloudCredentials` | Pass a `CloudCredentials` instance or configure DuckDB secrets externally |
| `ValueError: Unsupported format 'xlsx'` | Invalid format string | Use `"parquet"`, `"ndjson"`, `"json"`, or `"iceberg"` |
