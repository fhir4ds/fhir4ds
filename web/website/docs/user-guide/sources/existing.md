---
id: existing
title: Existing Table Source
sidebar_label: Existing Tables
---

# Existing Table Source

The `ExistingTableSource` allows you to use data that has already been loaded into DuckDB, while still adhering to the standard `SourceAdapter` lifecycle.

## Usage

```python
from fhir4ds.sources import ExistingTableSource

# Connect to a DuckDB file that already contains clinical data
con = fhir4ds.create_connection("production_lake.db")

# Wrap the existing 'raw_resources' table
source = ExistingTableSource("raw_resources")

fhir4ds.attach(con, source)
```

## Legacy Support

This adapter provides a bridge for users still utilizing the `FHIRDataLoader` pattern or custom ETL scripts. It performs schema validation to ensure the table contains the required `id`, `resourceType`, `resource`, and `patient_ref` columns before allowing clinical queries to proceed.
