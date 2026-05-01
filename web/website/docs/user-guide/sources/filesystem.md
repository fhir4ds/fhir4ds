---
id: filesystem
title: File System Source
sidebar_label: Local & Cloud Files
---

# File System Source

The `FileSystemSource` is the most common way to use FHIR4DS. it allows you to query directories of FHIR resources directly without any data loading step.

## Usage

```python
from fhir4ds.sources import FileSystemSource

# Local glob pattern
source = FileSystemSource("data/fhir-output/**/*.ndjson")

# Cloud storage (S3, GCS, Azure)
source = FileSystemSource("s3://my-bucket/bulk-export/*.parquet")
```

## Supported Formats

The adapter automatically detects the file format based on the extension:

*   **JSON**: Standard FHIR JSON resources or bundles.
*   **NDJSON**: Newline-delimited JSON (standard FHIR bulk data).
*   **Parquet**: High-performance columnar storage.
*   **Iceberg**: Managed analytical tables.

## Cloud Credentials

To access private cloud buckets, use the `CloudCredentials` helper:

```python
from fhir4ds.sources import FileSystemSource, CloudCredentials

creds = CloudCredentials(
    provider="S3",
    access_key_id="...",
    secret_access_key="..."
)

source = FileSystemSource("s3://my-private-bucket/*.ndjson", credentials=creds)
```

## Performance Note

This adapter uses DuckDB's native C++ scanners. For very large datasets, the engine streams data directly from disk, allowing you to run population-scale analytics on datasets much larger than your available RAM.
