# fhir4ds.sources — Zero-ETL Source Adapters

## Overview

`fhir4ds.sources` provides a unified **SourceAdapter** interface that allows
`fhir4ds` to evaluate CQL measures and FHIRPath queries directly against
external data sources — Parquet files, NDJSON exports, Postgres databases,
Mongo-backed FHIR servers, or CSV files — without copying data into a local
DuckDB file.

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
| `HapiPostgresSource` | `hapi_postgres.py` | HAPI FHIR JPA Server on PostgreSQL |
| `MongoFhirServerSource` | `mongo_fhir.py` | Mongo-backed FHIR servers via DuckDB `mongo_scan` |
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
├── hapi_postgres.py  # HapiPostgresSource, HapiPostgresSchema
├── mongo_fhir.py     # MongoFhirServerSource, MongoFhirServerSchema
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
- Mongo source URIs, database names, collection names, JSON paths, and filter
  documents must be passed as SQL string literals with `quote_sql_literal()`;
  never interpolate them raw into `mongo_scan`.
- Mongo filter documents must be built as Python mappings and serialized with
  `json.dumps`; do not hand-build JSON filter strings.
- Mongo error messages must use redacted connection strings. Keep credential and
  sensitive query parameter redaction tests when changing `mongo_fhir.py`.
- Milestone code review finding (2026-05-20, FIXED): `CSVSource` quotes the
  CSV path with `quote_sql_literal()` before substituting it into
  `read_csv_auto(...)`. Keep the malicious-path regression test covering
  `'); DROP TABLE ...; --` patterns when changing the adapter.

## API Contract Notes

- `CSVSource` validates `path` and `projection_sql` at construction time.
  Invalid argument types must raise `TypeError`, and empty strings must raise
  `ValueError`; do not let bad public constructor inputs fall through to
  internal `AttributeError` during `register()`.
- `MongoFhirServerSchema` supports `per_resource`, `explicit`, and `shared`
  collection layouts. Preserve explicit `resource_path`, `id_path`, and
  `resource_type_path` configurability when changing collection projection SQL.
- Keep `MongoFhirServerSource` read-only. HAPI-like queue processing,
  change-stream watching, and generated MeasureReport writes belong in
  `fhir4ds/dqm/mongo_materialization.py`, not in the source adapter.
- Mongo integration tests are environment-gated. Use
  `FHIR4DS_RUN_MONGO_INTEGRATION=1`, `FHIR4DS_MONGO_URI`, and
  `FHIR4DS_MONGO_DATABASE` for live extension/database checks; skips are
  appropriate only when the Mongo service, `mongosh`, or DuckDB community
  extension is unavailable.

## Known Limitations (Phase 6: Incremental Delta Tracking)

`PostgresSource.get_changed_patients()` only detects updates/inserts. Hard
deletes require soft-delete patterns with an `updated_at` timestamp.

`FileSystemSource.get_changed_patients()` uses file mtime, which is not a
reliable proxy for patient-level data changes — a file touched without data
changes produces false positives.

See the `ReactiveEvaluator` documentation for full limitations.
