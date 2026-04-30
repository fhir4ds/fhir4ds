---
id: data-sources
title: Data Sources & Zero-ETL
sidebar_label: Data Sources
---

# Data Sources & Zero-ETL

FHIR4DS uses a **Zero-ETL** architecture. Instead of requiring you to load FHIR data into a specialized database schema, FHIR4DS can "attach" to your data where it already lives—whether that is in local files, cloud storage, or an existing PostgreSQL database.

## 1. The `resources` View

The clinical reasoning engine (CQL, FHIRPath, and ViewDefinitions) is designed to query a virtual view named `resources`. This view must provide the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `VARCHAR` | The logical ID of the FHIR resource. |
| `resourceType` | `VARCHAR` | The type of resource (e.g., `Patient`, `Observation`). |
| `resource` | `JSON` | The full FHIR resource as a JSON blob. |
| `patient_ref` | `VARCHAR` | The raw logical ID of the `Patient` this resource belongs to (e.g., `123`, not `Patient/123`). |

**Source Adapters** are responsible for mapping your underlying data format into this standard schema. Schema validation happens at registration time — if your data doesn't conform, you'll get a `SchemaValidationError` immediately, not during measure evaluation.

:::info Consistent Patient References
While some FHIR tools use prefixed references (like `Patient/123`), FHIR4DS uses **raw IDs** for `patient_ref` to maximize join performance and simplify SQL projections.
:::

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
    source=FileSystemSource("./data/**/*.ndjson", format="ndjson")
)
```

### Dynamic Attachment
You can also swap data sources on an active connection:

```python
from fhir4ds.sources import FileSystemSource, CSVSource

# Attach local files
ndjson_source = FileSystemSource("./data/*.ndjson", format="ndjson")
fhir4ds.attach(con, ndjson_source)

# ... run measures ...

# Detach and switch to a CSV source
fhir4ds.detach(con, ndjson_source)

csv_source = CSVSource(
    path="./exports/patients.csv",
    projection_sql="""
        SELECT
            patient_id AS id,
            'Patient' AS resourceType,
            json_object('resourceType', 'Patient', 'id', patient_id) AS resource,
            patient_id AS patient_ref
        FROM {source}
    """
)
fhir4ds.attach(con, csv_source)
```

---

## 3. Which Approach Should I Use?

| Scenario | Recommended Approach |
|----------|---------------------|
| Quick analysis of Parquet/NDJSON files | `FileSystemSource` — zero setup, mount and query |
| S3/Azure/GCS data lake | `FileSystemSource` with `CloudCredentials` |
| FHIR JSON stored in PostgreSQL | `PostgresSource` with `PostgresTableMapping` |
| Flat CSV files that need FHIR JSON construction | `CSVSource` with a projection SQL |
| Already loaded data via `FHIRDataLoader` | `ExistingTableSource` for adapter API uniformity |
| Already loaded data, no adapter API needed | Use `FHIRDataLoader` directly — no adapter required |

:::tip 

Source Adapters vs FHIRDataLoader
Source adapters are the **preferred pattern** for enterprise use cases — they provide a uniform API, schema validation at registration time, and dynamic attach/detach. `FHIRDataLoader` remains fully supported and is simpler for quick, script-based workflows.
:::

---

## 4. Core Adapters

### Local & Cloud Files (`FileSystemSource`)
Reads FHIR data from local or remote files (S3, GCS, Azure). Supports **Parquet** (default), **NDJSON**, **JSON**, and **Iceberg**.

*   **Best for:** Synthetic data, bulk exports, and data lakes.
*   **Performance:** Native C++ streaming from disk.

```python
from fhir4ds.sources import FileSystemSource

source = FileSystemSource("s3://my-bucket/fhir-bulk-export/*.parquet")
fhir4ds.attach(con, source)
```

### PostgreSQL (`PostgresSource`)
Connects directly to a PostgreSQL database where FHIR resources are stored as JSON/JSONB in a column.

*   **Best for:** Production database clones or existing clinical warehouses.

:::caution

`PostgresSource` requires FHIR JSON in a Postgres column. It does not construct FHIR JSON from arbitrary relational schemas.

:::

### CSV Files (`CSVSource`)
Maps flat CSV files to the FHIR schema using a user-defined SQL projection.

*   **Best for:** Legacy exports, spreadsheets, or one-off analyses.

### Existing Tables (`ExistingTableSource`)
Wraps pre-loaded DuckDB tables in the adapter API for uniform lifecycle management.

---

## 5. Managing Terminology

Clinical logic often relies on **ValueSets** to define sets of codes. Regardless of your data source, you must load your terminology expansions so the engine can resolve them locally.

```python
# Terminology is loaded into the connection's internal cache
con = fhir4ds.create_connection(
    source=FileSystemSource("./data/**/*.parquet"),
    valueset_cache=my_expanded_codes
)
```

:::info 

"Failing Fast" vs "Data Resiliency"

FHIR4DS adheres to a **Fail Fast** philosophy for logic: if your CQL or Source configuration is invalid, the engine will stop immediately. However, it provides **Data Resiliency** for rows: if a specific resource in your data is malformed, that row will be handled gracefully (returning NULL) without crashing the entire population query.

:::