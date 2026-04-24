---
id: viewdef
title: viewdef
sidebar_label: viewdef
---

# `fhir4ds.viewdef`

HL7 SQL-on-FHIR v2 ViewDefinition implementation for DuckDB.

## 1. At a Glance

Core entry points for flattening FHIR:

```python
from fhir4ds.viewdef import (
    SQLGenerator,           # Core generator class
    parse_view_definition,  # Validator and parser
)
```

---

## 2. Class Reference

### `SQLGenerator`
`SQLGenerator(dialect='duckdb', *, strict_collection=False, source_table=None)`

Generates optimized SQL from a validated ViewDefinition AST.

#### Methods

- **`generate(view_definition) -> str`**: Main entry point. Generates DuckDB SQL from a ViewDefinition object.
- **`generate_from_json(json_str) -> str`**: Convenience method that parses JSON and generates SQL in one step.

---

## 3. Configuration & Logic

### Generator Options
The constructor accepts:
- `dialect`: (Default: `"duckdb"`) The SQL dialect to target.
- `strict_collection`: (Default: `False`) Enable strict collection semantics.
- `source_table`: (Default: `None`) Override the source table name. When set, the generated SQL reads from this table instead of per-type pluralized tables.

### Flattening Strategies
- **`forEach`**: Translates to a **CROSS JOIN UNNEST**. Creates one row for every matching element. If the collection is empty, the parent row is omitted (Inner Join semantics).
- **`forEachOrNull`**: Translates to a **LEFT JOIN**. Preserves the parent row even if the sub-collection is empty.

---

## 4. Compliance

| Metric | Status |
|--------|--------|
| **SQL-on-FHIR v2 Spec** | **100% Compliance** (140 tests) |
| **Nested Selects** | Supported |
| **Recursive Joins** | Optimized via CTEs |
