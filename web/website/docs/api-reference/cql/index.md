---
id: cql
title: cql
sidebar_label: cql
---

# `fhir4ds.cql`

Clinical Quality Language (CQL) to SQL translator and measure evaluation engine.

## 1. At a Glance

The core components for CQL translation:

```python
from fhir4ds.cql import (
    CQLToSQLTranslator,   # The main translation engine
    FHIRDataLoader,       # Traditional data loading (ETL)
    translate_cql,         # Translate a CQL expression to SQL
    translate_library,     # Translate a CQL library
    register_udfs,         # Register clinical UDFs in DuckDB
)
```

---

## 2. Class Reference

### `FHIRDataLoader`
`FHIRDataLoader(con, table_name="resources", create_table=True)`

Automates the ingestion of FHIR resources into a SQL-native schema. While Zero-ETL is preferred for high performance, the loader is useful for small datasets or specialized preprocessing.

#### Methods
- **`load_file(path)`**: Load a single JSON file (Resource or Bundle).
- **`load_directory(path)`**: Recursively load all JSON/NDJSON files in a directory.
- **`load_ndjson(path)`**: Efficiently stream an NDJSON file into DuckDB.
- **`load_resource(resource_dict)`**: Insert a single FHIR resource dictionary.
- **`load_valuesets(valuesets)`**: Load expanded terminology for membership checks.

---

### `CQLToSQLTranslator`
`CQLToSQLTranslator(connection=None, audit_mode=False)`

The primary engine for converting clinical logic into vectorized database queries.

| Parameter | Type | Description |
|-----------|------|-------------|
| `connection` | `duckdb.DuckDBPyConnection` | (Optional) DuckDB connection for direct execution. |
| `audit_mode` | `bool` | (Optional) If True, emit audit structs wrapping boolean results. |

#### Methods

- **`translate_library_to_population_sql(library, output_columns=None, parameters=None, patient_ids=None) -> str`**: Converts a parsed CQL library into a single, multi-level DuckDB SQL statement.
- **`translate_library(library) -> dict`**: Translates all definitions in a CQL library. Returns a dict of definition names to SQL expressions.

---

## 3. Translation Internals

### The Pipeline
1.  **Parse**: Source CQL → ANTLR AST.
2.  **Resolve**: Context, Library, and Terminology resolution.
3.  **Generate**: AST Node → DuckDB SQL fragment.
4.  **Optimize**: Final SQL formatting and query plan hint injection.

### Audit Mode
Enable per-expression evidence capture by setting the audit flag in the translator context:

```python
translator.context.set_audit_mode(True)
sql = translator.translate_library_to_population_sql(lib)
```

---

## 4. SQL Primitive Reference

The following clinical primitives are registered in DuckDB via `fhir4ds.register()`:

- **Dates**: `AgeInYears()`, `AgeInMonths()`, `AgeInDays()`.
- **Intervals**: `intervalContains()`, `intervalOverlaps()`, `intervalStart()`.
- **Terminology**: `in_valueset()`.

---

## 5. Compliance & Profiles

| Standard | Support |
|----------|---------|
| **CQL Grammar** | 100% Compliance (3,044 tests) |
| **QI-Core** | v4.1.1 and v6.0.0 (2025) |
| **US Core** | v3.1.1 through v7.0.0 |
| **FHIR Version** | R4 (4.0.1) |
