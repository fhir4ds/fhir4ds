---
id: existing
title: Using Pre-Loaded Data
sidebar_label: Existing Tables
---

# Using Pre-Loaded Data

The `ExistingTableSource` adapter wraps a DuckDB table or view that you've already loaded — through `FHIRDataLoader`, custom ETL, or any other mechanism — into the standard source adapter API.

## Why ExistingTableSource Exists

If you're already using `FHIRDataLoader` to load FHIR data into DuckDB, your workflow doesn't need to change. `ExistingTableSource` exists to provide a **uniform API** so that code written against the adapter interface works identically whether data comes from files, Postgres, CSV, or pre-loaded tables.

## Quick Start

```python
import fhir4ds
from fhir4ds.sources import ExistingTableSource

con = fhir4ds.create_connection()

# Assume 'staged_fhir_data' was created via custom ETL
source = ExistingTableSource("staged_fhir_data")
fhir4ds.attach(con, source)

# A 'resources' view is now available for measures/FHIRPath
```

## Schema Requirements

The existing table or view must conform to the standard FHIR4DS schema contract (`id`, `resourceType`, `resource`, `patient_ref`). For details on the required types, see the [Data Sources & Zero-ETL Schema Contract](../data-sources#1-the-resources-view).

## FHIRDataLoader vs Adapter Approach

| Aspect | FHIRDataLoader Only | With ExistingTableSource |
|--------|---------------------|--------------------------|
| Data loading | `loader.load_directory(...)` | Same — `loader.load_directory(...)` |
| API pattern | Direct table access | `attach()` / `detach()` lifecycle |
| Schema validation | Manual | Automatic at `attach()` time |
| Swappable sources | No | Yes — same code works with any adapter |
| Breaking changes | None | None — additive only |

## Migration Path

If you're using `FHIRDataLoader` today, there are **no breaking changes**. To adopt the adapter pattern:

1. Keep your existing `FHIRDataLoader` code.
2. Add `ExistingTableSource()` and `fhir4ds.attach()` after loading.
3. Downstream code that uses `resources` works unchanged.

This is a **zero-risk migration** — `ExistingTableSource` validates the schema and passes through to the existing table.
