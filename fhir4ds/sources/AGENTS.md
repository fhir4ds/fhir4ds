# fhir4ds.sources — Zero-ETL Source Adapters

## Overview

`fhir4ds.sources` provides a unified **SourceAdapter** interface that allows
`fhir4ds` to evaluate CQL measures and FHIRPath queries directly against
external data sources — Parquet files, NDJSON exports, Postgres databases, or
CSV files — without copying data into a local DuckDB file.

## Architecture

Each adapter registers the external source as a DuckDB `resources` **view**
(never a table copy).  The view is schema-validated at registration time so
failures surface immediately, not during measure evaluation.

```
┌────────────────────────────────────────────┐
│  User Code                                 │
│  fhir4ds.create_connection(source=...)     │
│  fhir4ds.attach(con, adapter)              │
└──────────────┬─────────────────────────────┘
               │ calls register(con)
               ▼
┌────────────────────────────────────────────┐
│  SourceAdapter Protocol                    │
│  fhir4ds/sources/base.py                   │
└──────────────┬─────────────────────────────┘
               │ CREATE OR REPLACE VIEW resources AS ...
               ▼
┌────────────────────────────────────────────┐
│  DuckDB 'resources' View                   │
│  Schema: id, resourceType, resource,       │
│           patient_ref                      │
└──────────────┬─────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────┐
│  CQL / DQM / FHIRPath Engines              │
│  (query the view — no changes needed)      │
└────────────────────────────────────────────┘
```

## Available Adapters

| Adapter | Module | Use Case |
|---------|--------|----------|
| `ExistingTableSource` | `existing.py` | Wrap pre-loaded DuckDB table/view |
| `FileSystemSource` | `filesystem.py` | Parquet / NDJSON / Iceberg (local or cloud) |
| `PostgresSource` | `relational.py` | FHIR JSON stored in Postgres columns |
| `CSVSource` | `csv.py` | CSV files with user-defined SQL projection |

## Schema Contract

Every adapter must produce a view with exactly these columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `VARCHAR` | FHIR resource ID |
| `resourceType` | `VARCHAR` | FHIR resource type (e.g. `"Patient"`) |
| `resource` | `JSON` | Complete FHIR resource as JSON |
| `patient_ref` | `VARCHAR` | Patient ID this resource belongs to |

## File Structure

```
fhir4ds/sources/
├── __init__.py       # Exports all adapters and public API
├── base.py           # SourceAdapter Protocol, SchemaValidationError, helpers
├── existing.py       # ExistingTableSource
├── filesystem.py     # FileSystemSource, CloudCredentials
├── relational.py     # PostgresSource, PostgresTableMapping
├── csv.py            # CSVSource
└── tests/
    ├── unit/         # Unit tests per adapter
    └── integration/  # End-to-end API tests
```

## Adding a New Adapter

1. Create `fhir4ds/sources/<name>.py`
2. Implement a class with `register(con)` and `unregister(con)` methods
3. Call `validate_schema(con, self.__class__.__name__)` at the end of `register()`
4. Optionally implement `supports_incremental()` and `get_changed_patients()` for delta tracking
5. Register in `fhir4ds/sources/__init__.py` and add to `__all__`
6. Write unit tests covering: happy path, schema validation error, idempotency, unregister safety

## Security Notes

- All user-supplied identifiers must be quoted with `quote_identifier()` before interpolation
- Cloud storage paths are passed to DuckDB's own parser — never used as SQL identifiers
- `resource_type` string literals are escaped by doubling single quotes before interpolation
- Connection strings are passed to DuckDB's `ATTACH` — never interpolated into SQL statements

## Known Limitations (Phase 6: Incremental Delta Tracking)

`PostgresSource.get_changed_patients()` only detects updates/inserts. Hard
deletes require soft-delete patterns with an `updated_at` timestamp.

`FileSystemSource.get_changed_patients()` uses file mtime, which is not a
reliable proxy for patient-level data changes — a file touched without data
changes produces false positives.

See the `ReactiveEvaluator` documentation for full limitations.
