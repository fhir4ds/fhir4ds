# Feature Implementation Handoff: Mongo FHIR Server Source and Materialization

Status: implementation complete, ready for review

## Implemented

- Added `MongoFhirServerSource` in `fhir4ds/sources/mongo_fhir.py`.
- Added configurable `MongoFhirServerSchema` and `MongoResourceCollection`.
- Supported collection strategies:
  - `per_resource`
  - `explicit`
  - `shared`
- Added custom collection names, wrapped resource paths, shared `id` and
  `resourceType` paths, current filters, deleted filters, hidden-resource
  filtering, patient reference extraction, and private-field scrub.
- Kept runtime analytical reads on DuckDB community `mongo` extension and
  `mongo_scan`; no Python Mongo client is used by the read-only source adapter.
- Exported Mongo source classes from `fhir4ds.sources`.

## HAPI Parity Addition

User expanded scope during implementation: "we want parity with HAPI if
possible", including data-change handling and generated `MeasureReport` storage
back into Mongo.

Implemented this as a separate DQM materialization worker, not inside the
read-only source adapter:

- Added `fhir4ds/dqm/mongo_materialization.py`.
- Added optional dependency extra `fhir4ds-v2[mongo]` with `pymongo>=4.6`.
- Added `fhir4ds dqm mongo ...` CLI commands:
  - `install`
  - `sync-config`
  - `enqueue-patients`
  - `process-queue`
  - `listen`
  - `prune`
  - `status`
  - `reset-queue`
- Added Mongo-owned queue, run, result, report, audit, and measure-config
  collections.
- Added Mongo change-stream enqueueing as the Mongo-native analogue to HAPI
  PostgreSQL triggers and `LISTEN/NOTIFY`.
- Added generated individual `MeasureReport` tagging/identifier logic and
  optional upsert back into configured Mongo FHIR resource collections.
- Added generated MeasureReport self-loop guard for change-stream events.

Important parity caveat:

- Mongo does not support installable in-database triggers equivalent to
  PostgreSQL triggers. Change streams require a replica set or sharded cluster.
- Delete events only provide enough patient attribution for non-Patient
  resources when Mongo change stream pre-images are available.

## Docker and Docs

- Added `docker/mongo-fhir-server/`.
- Local Mongo stack uses `mongo:8.0.15` and a single-node replica set so change
  streams are available.
- Added seed fixture, source config example, materialization config example,
  worker Dockerfile, and smoke script.
- Added `scripts/mongo/smoke_mongo_source.py`.
- Updated repository docs:
  - `docs/mongo-fhir-server.md`
  - `fhir4ds/sources/README.md`
  - `fhir4ds/sources/AGENTS.md`
  - `README.md`
- Updated website docs and sidebars:
  - Mongo source user guide
  - Mongo integration page
  - Mongo source API reference
  - CLI docs
  - installation optional extras

## Patient-Scoped Source Pushdown Addition

User expanded scope after implementation: source reads should be limited to
the changed patients when HAPI or Mongo materialization workers detect patient
changes.

Implemented:

- Added `set_patient_scope()` / `clear_patient_scope()` to
  `HapiPostgresSource` and `MongoFhirServerSource`.
- HAPI decoded-view mode now rewrites the mounted `resources` view with a
  `patient_ref` predicate for the claimed batch.
- HAPI raw-table mode applies the same scope against the generated patient-ref
  expression.
- Mongo mode injects the claimed Patient IDs into `mongo_scan(filter := ...)`
  documents:
  - `Patient` resources filter by configured `id_path`.
  - Patient-bearing resources filter configured reference paths for local
    `Patient/<id>` references and absolute `http(s)://.../Patient/<id>`
    references.
- HAPI and Mongo materialization workers default
  `worker.source_patient_pushdown: true`.
- HAPI config also has `worker.source_patient_pushdown_mode: literal`;
  unsupported modes fail explicitly.
- Added `MeasureEvaluator.invalidate_prepared_statements()` so per-batch source
  view rewrites do not reuse prepared statements bound to a prior view shape.
- Added `fhir4ds dqm hapi explain-scope` to inspect the PostgreSQL plan for
  decoded-view patient pushdown.

## Tests Added

- `fhir4ds/sources/tests/unit/test_mongo_fhir.py`
- `fhir4ds/sources/tests/integration/test_mongo_fhir.py`
- `fhir4ds/dqm/tests/unit/test_mongo_materialization.py`
- Source integration import/API checks updated.

## Validation

- `python3 -m ruff check ...`: passed.
- `python3 -m py_compile ...`: passed.
- Focused test set:
  - 92 passed
  - 2 skipped live Mongo integration tests, gated by environment
- HAPI materialization unit regression file: passed.
- `python3 -m pytest fhir4ds/tests/test_version.py -q`: 2 passed.
- Website build: passed, with pre-existing Docusaurus warning about
  `vscode-languageserver-types`.
- Full conformance summary:
  - ViewDefinition: 134/134, 100.0%
  - FHIRPath R4: 935/935, 100.0%
  - CQL: 1706/1706, 100.0%
  - DQM QI Core 2025: 47/47, 100.0%
  - Overall: 2822/2822, 100.0%

Additional pushdown validation:

- Focused source/materialization/CLI test set: 97 passed.
- Live PostgreSQL 16 `EXPLAIN (ANALYZE, BUFFERS)` against a synthetic decoded
  resource table with a `patient_ref` index showed a `Bitmap Index Scan` with
  `patient_ref = ANY (...)` as the index condition.
- Website build: passed, with the pre-existing Docusaurus warning about
  `vscode-languageserver-types`.

## Review Focus

- Confirm that using private helper imports from `fhir4ds.sources.mongo_fhir`
  inside `mongo_materialization.py` is acceptable or should be promoted to a
  shared utility surface.
- Review Mongo change-stream delete semantics and documentation wording.
- Review generated MeasureReport upsert behavior for wrapped shared
  collections.
- Confirm whether future work should refactor common HAPI/Mongo
  materialization types into provider-neutral DQM materialization primitives.
