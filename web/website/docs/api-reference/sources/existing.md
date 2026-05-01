---
id: sources-existing
title: ExistingTableSource
sidebar_label: ExistingTableSource
---

# ExistingTableSource

`fhir4ds.sources.ExistingTableSource` — SourceAdapter for connections that already have a `resources` table or view loaded via `FHIRDataLoader` or any other mechanism.

## Purpose

ExistingTableSource provides API uniformity for users who already load data with `FHIRDataLoader`. It wraps pre-loaded data in the same `attach()`/`detach()` lifecycle without changing your workflow or duplicating data.

## Class Signature

```python
ExistingTableSource(table_name: str = "resources")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `table_name` | `str` | `"resources"` | Name of the existing DuckDB table or view containing FHIR resources. |

**Raises:** `SchemaValidationError` — if the existing table does not conform to the required schema (missing columns or wrong types).

---

## Methods

### `register(con)`

- When `table_name` differs from `"resources"`: creates a `CREATE OR REPLACE VIEW resources` projection over the named table.
- When `table_name` is `"resources"`: skips view creation and runs schema validation directly.

Always calls `validate_schema()` before returning.

### `unregister(con)`

Drops the `resources` view only if it was created by this adapter (i.e., when `table_name` was not `"resources"`). Safe to call even if `register()` was never called.

### `supports_incremental()`

Returns `False`. ExistingTableSource does not support incremental delta tracking.

---

## Examples

### Wrapping the Default `resources` Table

```python
import fhir4ds
from fhir4ds.cql.loader import FHIRDataLoader
from fhir4ds.sources import ExistingTableSource

con = fhir4ds.create_connection()

# Load data the traditional way
loader = FHIRDataLoader(con)
loader.load_directory('/data/fhir/')

# Wrap with the adapter API — validates schema immediately
source = ExistingTableSource()
fhir4ds.attach(con, source)
```

### Wrapping a Custom-Named Table

```python
# If your table is named something other than 'resources'
source = ExistingTableSource("my_fhir_table")
fhir4ds.attach(con, source)
# Now a 'resources' view exists that projects from 'my_fhir_table'
```

---

## When to Use This vs FHIRDataLoader Directly

| Scenario | Recommendation |
|----------|----------------|
| You want the simplest possible workflow | Use `FHIRDataLoader` directly — no adapter needed |
| You want a uniform API across all data sources | Wrap with `ExistingTableSource` |
| You're migrating to source adapters incrementally | `ExistingTableSource` is the bridge |
| You need to swap data sources dynamically | Use adapters with `attach()`/`detach()` |
