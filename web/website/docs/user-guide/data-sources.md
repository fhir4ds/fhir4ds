---
id: data-sources
title: Data Sources & Zero-ETL
sidebar_label: Data Sources
---

# Data Sources & Zero-ETL

FHIR4DS uses a **Zero-ETL** architecture. Instead of requiring you to load FHIR data into a specialized database schema, FHIR4DS can "attach" to your data where it already lives—whether that is in local files, cloud storage, or an existing relational database.

## 1. The `resources` View

The clinical reasoning engine (CQL, FHIRPath, and ViewDefinitions) is designed to query a virtual view named `resources`. This view must provide the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `VARCHAR` | The logical ID of the FHIR resource. |
| `resourceType` | `VARCHAR` | The type of resource (e.g., `Patient`, `Observation`). |
| `resource` | `JSON` | The full FHIR resource as a JSON blob. |
| `patient_ref` | `VARCHAR` | A normalized reference to the `Patient.id`. |

**Source Adapters** are responsible for mapping your underlying data format into this standard schema.

---

## 2. Attaching a Data Source

You can register a data source when creating a connection, or attach/detach them dynamically.

### Single-Step Connection
The easiest way to start is passing a `source` to `create_connection`:

```python
import fhir4ds
from fhir4ds.sources import FileSystemSource

# Connect and mount data in one line
con = fhir4ds.create_connection(
    source=FileSystemSource("./data/**/*.ndjson")
)
```

### Dynamic Attachment
You can also swap data sources on an active connection:

```python
from fhir4ds.sources import FileSystemSource, CSVSource

# Attach local files
fhir4ds.attach(con, FileSystemSource("./data/*.ndjson"))

# ... run measures ...

# Detach and switch to a CSV export
fhir4ds.detach(con)
fhir4ds.attach(con, CSVSource("./exports/measure_data.csv"))
```

---

## 3. Core Adapters

FHIR4DS provides several built-in adapters for common data science environments:

### Local & Cloud Files (`FileSystemSource`)
Reads FHIR data from local or remote files (S3, GCS, Azure). Supports **JSON**, **NDJSON**, **Parquet**, and **Iceberg**.

*   **Best for:** Synthetic data, bulk exports, and data lakes.
*   **Performance:** Native C++ streaming from disk.

```python
from fhir4ds.sources import FileSystemSource

source = FileSystemSource("s3://my-bucket/fhir-bulk-export/*.parquet")
fhir4ds.attach(con, source)
```

### Relational Databases (`PostgresSource`)
Connects directly to an existing SQL database where FHIR resources are stored in a JSONB or VARCHAR column.

*   **Best for:** Production database clones or existing warehouses.
*   **Databases:** PostgreSQL, MySQL, SQLite.

### Tabular FHIR (`CSVSource`)
Maps flat CSV files back into the FHIR schema. Useful for legacy exports or simplified spreadsheets.

---

## 4. Managing Terminology

Clinical logic often relies on **ValueSets** to define sets of codes. Regardless of your data source, you must load your terminology expansions so the engine can resolve them locally.

```python
# Terminology is loaded into the connection's internal cache
con = fhir4ds.create_connection(
    source=FileSystemSource("./data/"),
    valueset_cache=my_expanded_codes
)
```

:::info 

"Failing Fast" vs "Data Resiliency"

FHIR4DS adheres to a **Fail Fast** philosophy for logic: if your CQL or Source configuration is invalid, the engine will stop immediately. However, it provides **Data Resiliency** for rows: if a specific resource in your data is malformed, that row will be handled gracefully (returning NULL) without crashing the entire population query.

:::
