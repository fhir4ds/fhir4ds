---
id: filesystem
title: Querying Files & Data Lakes
sidebar_label: Local & Cloud Files
---

# Querying Files & Data Lakes

The `FileSystemSource` adapter lets you query directories of FHIR resources directly — no data loading step required. It works with local files and cloud object storage (S3, Azure Blob, GCS).

## Quick Start

```python
import fhir4ds
from fhir4ds.sources import FileSystemSource

# Mount a directory of Parquet files
con = fhir4ds.create_connection(
    source=FileSystemSource('/data/fhir/**/*.parquet')
)

# Run queries immediately
result = con.execute("""
    SELECT fhirpath_text(resource, 'Patient.name.given[0]') AS name
    FROM resources
    WHERE resourceType = 'Patient'
""").fetchdf()
```

## Supported Formats

| Format | Scanner | Notes |
|--------|---------|-------|
| **Parquet** (default) | `read_parquet()` | High-performance columnar storage. Best for large datasets. |
| **NDJSON** | `read_json_auto()` | Newline-delimited JSON — standard FHIR bulk data export format. |
| **JSON** | `read_json_auto()` | Standard JSON files. |
| **Iceberg** | `iceberg_scan()` | Apache Iceberg managed tables. |

:::note
The `format` parameter defaults to `"parquet"`. You must explicitly set it for other formats:

```python
source = FileSystemSource('/data/fhir/*.ndjson', format='ndjson')
```
:::

## Cloud Storage

To access private cloud buckets, use the `CloudCredentials` helper:

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
)
fhir4ds.attach(con, source)
```

**Supported providers:** `"S3"`, `"AZURE"`, `"GCS"`.

If you use a cloud URI without providing credentials, a `UserWarning` is emitted reminding you to configure DuckDB secrets externally.

## Hive Partitioning

For large datasets partitioned by `resourceType` or date, enable Hive partition pruning for significantly faster queries:

```python
# Data layout: /data/fhir/resourceType=Patient/*.parquet
source = FileSystemSource(
    '/data/fhir/**/*.parquet',
    hive_partitioning=True,
)
```

With Hive partitioning enabled, queries that filter on partition columns (e.g., `WHERE resourceType = 'Patient'`) read only the relevant partitions.

## Schema Requirements

Your source files (Parquet, NDJSON, etc.) must conform to the standard FHIR4DS schema contract, including the `id`, `resourceType`, `resource`, and `patient_ref` columns.

For a detailed description of the required types and formatting (specifically for `patient_ref`), see the [Data Sources & Zero-ETL Schema Contract](../data-sources#1-the-resources-view).

If any column is missing or has an incompatible type, `SchemaValidationError` is raised at registration time.

## Performance

FileSystemSource uses DuckDB's native C++ scanners. The engine streams data directly from disk, allowing population-scale analytics on datasets larger than available RAM.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `UserWarning: cloud URI but no credentials` | Pass a `CloudCredentials` instance, or configure DuckDB secrets before calling `register()`. |
| `SchemaValidationError: required column 'X' is missing` | Your source files must include all four required columns. |
| `ValueError: Unsupported format` | Use `"parquet"`, `"ndjson"`, `"json"`, or `"iceberg"`. |
| Type mismatch errors | Ensure your `resource` column contains valid JSON data. |