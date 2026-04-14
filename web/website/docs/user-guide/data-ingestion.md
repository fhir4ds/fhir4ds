---
id: data-ingestion
title: Data Ingestion & Terminology
sidebar_label: Data Ingestion
---

# Data Ingestion & Terminology

For FHIR4DS to evaluate clinical logic, data must be structured within DuckDB in a format optimized for analytical queries. The toolkit provides utilities to automate this process.

## 1. Storing FHIR Data

All clinical logic (FHIRPath and CQL) in FHIR4DS expects a table named `resources`. This table acts as the high-performance "clinical data lake" for the engine.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `VARCHAR` | The logical ID of the FHIR resource. |
| `resourceType` | `VARCHAR` | The type of resource (e.g., `Patient`, `Observation`). |
| `resource` | `JSON` | The full FHIR resource as a JSON blob. |
| `patient_ref` | `VARCHAR` | A normalized reference to the `Patient.id`. |

### Manual Table Creation
If you are managing your own schema, you can create the table manually:

```sql
CREATE TABLE resources (
    id VARCHAR,
    resourceType VARCHAR,
    resource JSON,
    patient_ref VARCHAR
);
```

---

## 2. Loading FHIR Data

The `FHIRDataLoader` class automates the ingestion of FHIR JSON, NDJSON, and Bundles into the clinical table.

### Basic Ingestion
You can load data from various sources using a single API:

```python
import fhir4ds
from fhir4ds.cql import FHIRDataLoader

con = fhir4ds.create_connection()
loader = FHIRDataLoader(con)

# Load a single JSON file (Resource or Bundle)
loader.load_file("./data/patient_alice.json")

# Load a directory of JSON/NDJSON files
loader.load_directory("./data/population/")

# Load from an NDJSON file
loader.load_ndjson("./data/large_batch.ndjson")
```

### Automatic Link Extraction
The loader automatically extracts the `patient_ref` (e.g., from `subject.reference`) to enable high-performance joins across resources during population analytics.

---

## 3. Managing Terminology

Clinical logic often relies on **ValueSets** to define sets of codes (e.g., "All Diabetes LOINC Codes"). FHIR4DS resolves these by loading expanded codes into a specialized lookup table.

### Loading ValueSet Codes
To use membership checks in your logic, you must load the expanded codes:

```python
# Expanded ValueSets are typically lists of dicts
valuesets = [
    {
        "url": "http://example.org/ValueSet/diabetes",
        "codes": [
            {"system": "http://loinc.org", "code": "123-4"},
            {"system": "http://loinc.org", "code": "567-8"}
        ]
    }
]

# Load into the local lookup table
loader.load_valuesets(valuesets)
```

### Local Resolution
Once loaded, FHIR4DS handles terminology resolution locally. This eliminates the need for an external terminology server during evaluation, ensuring the engine remains "zero-server" and production-accurate.

---

## 4. Putting It All Together

After ingesting data and terminology, you can run a measure evaluation:

```python
from fhir4ds.cql import FHIRDataLoader

# Step 1: Ingest FHIR data
loader = FHIRDataLoader(con)
loader.load_directory("./fhir-data/")

# Step 2: Load terminology (ValueSets)
loader.load_valuesets(valuesets)

# Step 3: Evaluate the measure
result = fhir4ds.evaluate_measure(
    library_path="./CMS165.cql",
    conn=con,
    parameters={"Measurement Period": ("2025-01-01", "2025-12-31")}
)
```

:::tip 

Performance Note
For large populations (100k+ patients), it is recommended to create indexes on the `patient_ref` and `resourceType` columns after data ingestion is complete to optimize query performance.

:::
