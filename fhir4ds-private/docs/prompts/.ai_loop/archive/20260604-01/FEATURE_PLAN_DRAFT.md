# Feature Plan Draft: Mongo FHIR Server Source

Status: Draft v1 for architecture self-audit

## Objective

Add a read-only MongoDB-backed FHIR server source adapter that mounts current
FHIR resources from a Mongo-backed FHIR server as the standard FHIR4DS
`resources` view:

```text
id VARCHAR
resourceType VARCHAR
resource JSON
patient_ref VARCHAR
```

The target initial server family is `icanbwell/fhir-server` / Helix FHIR Server.
The adapter must query MongoDB through DuckDB's community `mongo` extension, not
through a Python MongoDB client.

## Research Snapshot

- DuckDB documents the community `mongo` extension with `INSTALL mongo FROM
  community; LOAD mongo;`, `ATTACH ... (TYPE MONGO)`, and a `mongo_scan(...)`
  table function with optional `filter` and `sample_size` parameters.
- The upstream `icanbwell/fhir-server` repository describes Helix FHIR Server as
  a MongoDB-backed FHIR server with GraphQL, event streams, delayed history and
  audit processing, and support for all FHIR resources.
- A temporary source checkout at commit
  `1bb6a360bf7d199ee31787c65b42a2e5ffc75594` shows current resources are stored
  in per-resource collections named `{ResourceType}_{base_version}`, for example
  `Patient_4_0_0`.
- The same checkout shows history collections are named
  `{ResourceType}_{base_version}_History` and may be stored in a separate
  `resource-history` database.
- Delete handling writes a history entry, then physically deletes the current
  document from the current collection.
- Normal search excludes resources with `meta.tag` containing
  `system=https://fhir.icanbwell.com/4_0_0/CodeSystem/server-behavior` and
  `code=hidden`, unless `_includeHidden` is requested.

## Spec Alignment

- FHIR R4 Resource: every resource has a logical `id`, `meta`, and a JSON
  `resourceType` discriminator.
- FHIR R4 JSON: a resource is a JSON object with a `resourceType` property.
- FHIR R4 Reference: `Reference.reference` may be a relative reference such as
  `Patient/123`, which is the only form converted into the FHIR4DS raw
  `patient_ref` value.
- FHIR4DS source adapter contract: adapters register a DuckDB view called
  `resources`, validate the exact schema at registration time, and remain
  read-only.

## Proposed Architecture

Add `fhir4ds/sources/mongo_fhir.py` with:

- `MongoFhirServerSchema`, a frozen dataclass describing database name,
  collection strategy, FHIR base version suffix, hidden-resource policy, sample
  size, and patient-reference extraction paths.
- `MongoFhirServerSource`, a `SourceAdapter` implementation with `register()`,
  `unregister()`, `supports_incremental()`, and no write operations.

The source registers a `resources` view by unioning `mongo_scan(...)` selects.
For the Helix default strategy, collection names are derived as
`{resourceType}_{base_version}`. Alternative explicit collection mappings are
supported for deployments that do not follow that convention.

## Draft API

```python
from fhir4ds.sources import MongoFhirServerSource, MongoFhirServerSchema

source = MongoFhirServerSource(
    "mongodb://localhost:27017",
    schema=MongoFhirServerSchema(
        database_name="fhir",
        base_version="4_0_0",
        resource_types=("Patient", "Observation"),
    ),
)
fhir4ds.attach(con, source)
```

## Implementation Plan

1. Add `MongoFhirServerSchema` and constructor validation.
2. Add SQL generation helpers using `quote_identifier()` for identifiers and
   `quote_sql_literal()` for URI, database, collection, and JSON filter string
   literals.
3. Add safe JSON filter generation with `json.dumps`, never manual string
   concatenation.
4. Build one `mongo_scan(...)` select per configured collection and `UNION ALL`
   them into `CREATE OR REPLACE VIEW resources AS ...`.
5. Derive `patient_ref` from `Patient` ids and configured reference paths.
6. Register the adapter in `fhir4ds/sources/__init__.py`, source README, website
   docs, and API reference.
7. Add a Docker workflow under `docker/mongo-fhir-server`.
8. Add unit tests and environment-gated integration/smoke tests.

## Test Strategy

- Unit tests for constructor validation, SQL generation, idempotent register,
  unregister safety, schema validation, patient reference extraction, hidden tag
  filters, and SQL injection attempts.
- Integration tests for `INSTALL mongo FROM community; LOAD mongo;`,
  Mongo-backed `resources` row shape, FHIRPath over mounted resources, and a
  minimal DQM/CQL smoke.
- Docker smoke for Mongo-only direct seed and full Helix FHIR server when
  practical.

## Known Draft Risks

- The draft must define a stricter collection discovery/failure policy so the
  implementation never analyzes the wrong collections.
- The draft must address DuckDB Mongo schema inference and how complete resource
  JSON is preserved when sparse fields are outside the inference sample.
- The draft must make hidden-resource behavior explicit and testable.
- The draft must include credential redaction rules for all exceptions, docs,
  and smoke output.
