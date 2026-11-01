# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Build a MongoDB-backed FHIR server integration parallel to the existing HAPI
PostgreSQL integration, targeting Mongo-backed FHIR servers such as
`icanbwell/fhir-server` / Helix FHIR Server. The integration should let FHIR4DS
query current FHIR resources in place through DuckDB using the community
`mongo` extension, expose the standard FHIR4DS `resources` view, and provide a
Docker-based development/smoke stack comparable to `docker/hapi-postgres`.

Primary outcome: a read-only zero-ETL Mongo FHIR source plus local Docker
workflow that can run FHIRPath/CQL/DQM smoke checks against MongoDB-hosted FHIR
resources without exporting NDJSON or copying PHI into a local DuckDB file.

## Pipeline
1. feature_design
2. feature_implementation
3. code_review
4. pre_release
5. docs_audit

## Feature Plan

No pre-approved implementation plan exists yet. Start with `feature_design` and
produce a refined design for user approval before implementation.

### External Reference Points

- Target FHIR server family: `https://github.com/icanbwell/fhir-server`
  - The upstream project describes itself as a highly scalable FHIR server
    backed by MongoDB, with real-time data streaming, change event tracking,
    GraphQL, all FHIR resource support, and delayed history/audit processing.
  - Its current Docker Compose reference uses `MONGO_URL=mongodb://mongo:27017`
    and `MONGO_DB_NAME=fhir`, plus separate Mongo databases for resource history
    and audit events. The exact current-resource collection layout must be
    discovered from a running fixture or source inspection before hardcoding any
    schema assumptions.
- DuckDB connector: `https://duckdb.org/community_extensions/extensions/mongo`
  - Install/load syntax: `INSTALL mongo FROM community; LOAD mongo;`
  - Attach syntax example: `ATTACH 'host=localhost port=27017' AS mongo_db (TYPE MONGO);`
  - Scan function example:
    `mongo_scan('mongodb://localhost:27017', 'mydb', 'mycollection', filter := '{"status":"active"}')`
  - The connector provides direct SQL access to MongoDB collections, automatic
    schema inference, and filter pushdown. Design must verify how nested BSON
    FHIR resources are surfaced in DuckDB before choosing the final projection.

### Scope

1. Add a new source adapter, tentatively named `MongoFhirServerSource`, under
   `fhir4ds/sources/`.
2. The adapter must register a DuckDB `resources` view with the established
   schema contract:
   - `id VARCHAR`
   - `resourceType VARCHAR`
   - `resource JSON`
   - `patient_ref VARCHAR`
3. The adapter must use DuckDB's community `mongo` extension, not a Python
   MongoDB client, for analytical reads. A Python client may be used only for
   optional test seeding or smoke helpers if justified by the design.
4. Support configurable Mongo connection details:
   - URI or host/port attachment string
   - database name, defaulting to `fhir`
   - current-resource collection strategy after discovery:
     - one collection per FHIR resource type, or
     - one shared resource collection filtered by `resourceType`, or
     - explicit user-supplied collection mapping
   - optional sample size/schema-inference setting if the DuckDB extension
     requires it for stable nested-field inference.
5. Patient attribution must mirror existing source adapters:
   - `Patient` resources use their own FHIR id.
   - Other resources check configurable local reference paths, initially
     `subject.reference`, `patient.reference`, and `beneficiary.reference`.
   - Only local references such as `Patient/<id>` become raw patient ids.
6. Current-resource semantics must be explicit:
   - Discover how `icanbwell/fhir-server` stores active/current resources,
     deleted resources, versions/history, and audit data.
   - V1 should query current non-deleted resources only.
   - If current/deleted semantics cannot be proven, fail clearly rather than
     silently analyzing stale, historical, or deleted records.
7. Keep V1 read-only. Do not modify MongoDB collections from the adapter.
8. Treat Mongo change streams or event-driven DQM materialization as a possible
   follow-up phase. Do not build a trigger/change-stream worker in V1 unless
   the feature design proves a small, stable contract comparable to the HAPI
   materialization queue.

### Docker Deliverables

Create a Docker workflow parallel to `docker/hapi-postgres`, tentatively under
`docker/mongo-fhir-server/`.

Minimum expected artifacts:

- `docker-compose.yml` for a disposable local Mongo FHIR integration stack.
- A MongoDB service, pinned to an explicit image tag.
- A FHIR server service based on `icanbwell/fhir-server` when practical:
  - Prefer a pinned published image if one is available and verifiably usable.
  - Otherwise document and automate local source build steps.
  - Include only required companion services for the smoke path. If the full
    upstream stack requires Keycloak, Redis, Kafka, or ClickHouse, isolate those
    behind an optional Compose profile and document why.
- Optional FHIR4DS worker/smoke container profile, similar to the HAPI worker
  profile, with `fhir4ds-v2` plus any required optional extras installed.
- Example config files for the source adapter and smoke scripts.
- A smoke path that can:
  - start the stack,
  - load a small FHIR R4 fixture through FHIR REST when the server is running,
    or directly seed Mongo only for adapter-level tests,
  - register the Mongo source,
  - query the `resources` view,
  - run at least one FHIRPath smoke and one DQM/CQL smoke against the mounted
    Mongo-backed resources.

### Implementation Constraints

- Follow `fhir4ds/sources/AGENTS.md` and existing source adapter patterns.
- Quote identifiers and SQL string literals separately using the shared source
  helpers. Mongo URIs, database names, collection names, attachment names,
  patient ids, and JSON filter strings must not be interpolated unsafely.
- Do not leak credentials in exception messages, CLI output, docs examples
  beyond local disposable defaults, or status commands.
- Skip tests only for environment availability, such as missing Docker, missing
  MongoDB, or unavailable DuckDB community extension installation.
- Do not remove `-p no:benchmark` from pytest options. Benchmark runs remain
  script-driven.
- If package metadata, optional dependencies, Docker image contents, CLI
  commands, docs navigation, or release artifacts change, the final validation
  must include the release/artifact gate after implementation.

### Documentation Deliverables

- Repository docs for the Mongo FHIR server workflow, parallel to:
  - `docs/hapi-materialization.md`
  - `docs/hapi-pilot-runbook.md`
  - `docker/hapi-postgres/README.md`
- Website docs under `web/website/docs/` for:
  - the Mongo source adapter user guide,
  - any DQM/materialization workflow that is actually implemented,
  - API reference for the new adapter.
- Update `web/website/sidebars.ts` when adding website docs so the pages are
  visible in the UI.
- Update `fhir4ds/sources/README.md`, `fhir4ds/sources/AGENTS.md`, and public
  package exports when the adapter is added.

### Verification Expectations

- Unit tests for:
  - adapter constructor validation,
  - SQL generation/quoting,
  - standard `resources` schema validation,
  - idempotent register/unregister behavior,
  - patient reference extraction,
  - malicious URI/database/collection/patient-reference inputs.
- Integration tests or smoke scripts for:
  - `INSTALL mongo FROM community; LOAD mongo;`
  - Mongo-backed `resources` view row shape,
  - FHIRPath query against mounted resources,
  - DQM/CQL smoke against a small patient fixture.
- Docker smoke validation for the new stack when Docker is available.
- Website build if website docs/sidebar files change.
- Focused full-package tests if shared source adapter contracts or public
  `fhir4ds.attach()` behavior change.

## Focus Areas

- Discovery first: do not assume `icanbwell/fhir-server` collection names or
  deleted/current-resource markers without proving them.
- Keep the first implementation read-only and zero-ETL.
- Preserve the `resources` view contract exactly so existing FHIRPath, CQL,
  ViewDefinition, and DQM code paths do not need source-specific branches.
- Treat the DuckDB Mongo extension as an optional/community dependency with
  clear errors and environment-gated tests.
- Match the HAPI integration's developer ergonomics: local Docker stack,
  smoke script, example config, docs, and website navigation.
- Security review is mandatory around SQL construction, Mongo connection
  strings, credentials, and generated JSON filters.
