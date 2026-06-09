# Feature Plan: Mongo FHIR Server Source

Status: Implemented and ready for review
Target package version: 0.0.7

## Objective

Build a read-only, zero-ETL MongoDB FHIR server source adapter that lets FHIR4DS
query current FHIR resources in place through DuckDB. The adapter must expose
the standard FHIR4DS `resources` view so existing FHIRPath, CQL,
ViewDefinition, and DQM paths continue to work without Mongo-specific branches.

Primary target: Mongo-backed FHIR servers in the `icanbwell/fhir-server` /
Helix FHIR Server family.

## Scope Boundaries

- Do not write to MongoDB from the `MongoFhirServerSource` adapter; it remains a
  read-only source adapter.
- HAPI-like DQM materialization parity is implemented as a separate Mongo worker
  in `fhir4ds.dqm.mongo_materialization`.
- Do not use a Python MongoDB client for runtime analytical reads.
- Do not copy PHI into local DuckDB tables.
- Do not hardcode a generic all-FHIR-resource list in runtime logic.
- Mongo does not support PostgreSQL-style installable triggers. Data-change
  wakeups use Mongo change streams and require a replica set or sharded cluster.

## Research Findings

External references:

- DuckDB community `mongo` extension:
  `https://duckdb.org/community_extensions/extensions/mongo`
- DuckDB extension installation model:
  `https://duckdb.org/docs/current/extensions/overview`
- HL7 FHIR R4 Resource:
  `https://hl7.org/fhir/R4/resource.html`
- HL7 FHIR R4 JSON representation:
  `https://hl7.org/fhir/R4/json.html`
- HL7 FHIR R4 Reference:
  `https://hl7.org/fhir/R4/references.html`
- Upstream target repository:
  `https://github.com/icanbwell/fhir-server`

Local source inspection:

- Existing adapter contract lives in `fhir4ds/sources/base.py`.
- Existing HAPI source pattern lives in `fhir4ds/sources/hapi_postgres.py`.
- Source adapter rules live in `fhir4ds/sources/AGENTS.md`.
- A temporary upstream checkout of `icanbwell/fhir-server` at commit
  `1bb6a360bf7d199ee31787c65b42a2e5ffc75594` was inspected.

Helix storage findings from source inspection:

- Current resources use per-resource collections named
  `{ResourceType}_{base_version}`, for example `Patient_4_0_0`.
- History collections use `{ResourceType}_{base_version}_History`.
- The upstream compose defaults include `MONGO_DB_NAME=fhir`,
  `RESOURCE_HISTORY_MONGO_DB_NAME=resource-history`, and Mongo image
  `mongo:8.0.15`.
- Delete handling writes history first and then physically deletes current
  documents from the current collection.
- Normal search excludes resources tagged with
  `system=https://fhir.icanbwell.com/4_0_0/CodeSystem/server-behavior` and
  `code=hidden`, unless hidden resources are explicitly included.

## Architecture

Add `fhir4ds/sources/mongo_fhir.py`.

Public exports:

- `MongoFhirServerSource`
- `MongoFhirServerSchema`
- `MongoResourceCollection`
- Optional `MongoCollectionStrategy` literal alias if useful locally.

Materialization parity additions:

- `fhir4ds.dqm.mongo_materialization`
- `fhir4ds dqm mongo install`
- `fhir4ds dqm mongo sync-config`
- `fhir4ds dqm mongo enqueue-patients`
- `fhir4ds dqm mongo process-queue`
- `fhir4ds dqm mongo listen`
- `fhir4ds dqm mongo status`
- `fhir4ds dqm mongo reset-queue`

The adapter registers a DuckDB view named `resources` and calls
`validate_schema(con, self.__class__.__name__)` before `register()` returns.
`unregister()` drops `resources` and detaches any adapter-created DuckDB Mongo
attachment. The adapter should report `supports_incremental() is False` in V1.

### Proposed API

```python
from fhir4ds.sources import MongoFhirServerSchema, MongoFhirServerSource

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

Explicit non-default collection layout:

```python
from fhir4ds.sources import (
    MongoFhirServerSchema,
    MongoFhirServerSource,
    MongoResourceCollection,
)

source = MongoFhirServerSource(
    "mongodb://analytics-user:secret@mongo.example.org:27017",
    schema=MongoFhirServerSchema(
        database_name="clinical_fhir",
        collection_strategy="explicit",
        collections=(
            MongoResourceCollection(
                resource_type="Patient",
                collection_name="current_patients",
                resource_path="$",
                current_filter={"deleted": {"$ne": True}},
            ),
            MongoResourceCollection(
                resource_type="Observation",
                collection_name="current_observations",
                resource_path="$.resource",
                id_path="$.resource.id",
                resource_type_path="$.resource.resourceType",
                current_filter={"status": {"$ne": "deleted"}},
            ),
        ),
    ),
)
```

Schema shape:

```python
@dataclass(frozen=True)
class MongoResourceCollection:
    resource_type: str
    collection_name: str
    resource_path: str = "$"
    id_path: str = "$.id"
    resource_type_path: str = "$.resourceType"
    current_filter: Mapping[str, Any] | None = None
    deleted_filter: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class MongoFhirServerSchema:
    database_name: str = "fhir"
    base_version: str = "4_0_0"
    collection_strategy: Literal["per_resource", "explicit", "shared"] = "per_resource"
    resource_types: tuple[str, ...] | None = None
    collections: tuple[MongoResourceCollection, ...] | None = None
    collection_mappings: Mapping[str, str] | None = None  # shorthand for default paths
    shared_collection: str | None = None
    shared_resource_path: str = "$"
    shared_id_path: str = "$.id"
    shared_resource_type_path: str = "$.resourceType"
    shared_current_filter: Mapping[str, Any] | None = None
    shared_deleted_filter: Mapping[str, Any] | None = None
    sample_size: int | None = -1
    include_hidden: bool = False
    hidden_tag_system: str = "https://fhir.icanbwell.com/4_0_0/CodeSystem/server-behavior"
    hidden_tag_code: str = "hidden"
    patient_reference_paths: tuple[str, ...] = (
        "$.subject.reference",
        "$.patient.reference",
        "$.beneficiary.reference",
    )
    scrub_private_fields: tuple[str, ...] = (
        "_id",
        "_uuid",
        "_sourceId",
        "_sourceAssigningAuthority",
    )
```

Constructor notes:

- `connection_string` is a Mongo URI for `mongo_scan(...)`.
- `attachment_name` defaults to `fhir4ds_mongo`.
- `install_extension` defaults to `True`.
- Argument validation must reject non-string and empty URI/database/collection
  values at construction time where possible.
- Collection strategies:
  - `per_resource`: build collection names as `{resourceType}_{base_version}`.
  - `explicit`: use `collections` for full layout control, or
    `collection_mappings[resourceType]` as a shorthand when the FHIR resource is
    the root Mongo document.
  - `shared`: scan one `shared_collection` and filter by `resourceType`.
- `resource_path`, `id_path`, and `resource_type_path` are JSON paths into the
  Mongo document after `mongo_scan` materializes a row. They exist because some
  deployments store the FHIR resource as the whole document and others wrap it
  under fields such as `resource`, `payload`, or `entry.resource`.
- `current_filter` and `deleted_filter` are Mongo filters expressed as Python
  mappings and serialized with `json.dumps()`. They allow deployments with
  soft-delete flags, tenant partitions, or current-version markers to configure
  current-resource semantics without code changes.
- For V1, filters are conjunctive. The adapter should combine:
  configured current filters, configured deleted-resource exclusions, hidden-tag
  exclusions, shared-collection `resourceType` filters, and any future
  adapter-owned safety predicates with `$and`.

## Layout Configurability

MongoDB has collections rather than SQL tables, but DuckDB may expose attached
Mongo collections through table-like catalog metadata. The adapter should use
"collection" in Python APIs and docs, while recognizing that users may think of
them as table names from the DuckDB side.

The design should optimize for configurable layouts, not one baked-in Helix
schema:

- Helix default: current resources in per-resource collections such as
  `Patient_4_0_0`.
- Explicit current collections: user maps `Patient -> current_patients`,
  `Observation -> current_observations`, and so on.
- Wrapped-resource documents: user points `resource_path` at the embedded FHIR
  JSON object.
- Shared collection: user points all resource types at one collection and the
  adapter adds a `resourceType` filter.
- Soft-delete/current-version fields: user supplies `current_filter` or
  `deleted_filter` mappings instead of requiring code changes.

This must still be configuration, not arbitrary user-provided SQL. The adapter
owns SQL generation so identifier/literal quoting, filter serialization,
credential redaction, and schema validation remain centralized.

## Current-Resource Semantics

V1 must not guess.

Implementation rules:

- If `resource_types`, `collections`, and `collection_mappings` are all absent,
  attempt catalog discovery after `ATTACH`. Accept discovered collections only
  if the extension exposes them through DuckDB catalog metadata and their names
  match `^{ResourceType}_{base_version}$`.
- If discovery is unavailable or ambiguous, raise an actionable error telling
  the user to pass `resource_types`, `collections`, or `collection_mappings`.
- If current/deleted semantics require deployment-specific flags, the user must
  configure `current_filter` or `deleted_filter`. Do not infer soft-delete field
  names from data heuristics.
- Never include collections ending in `_History` unless a future feature plan
  explicitly designs history support.
- Never scan audit, access-log, or resource-history databases by default.
- For Helix-compatible schemas, default hidden-resource behavior mirrors normal
  search by excluding the server-behavior hidden tag. Users may opt into
  `include_hidden=True`.

Acceptance criteria:

- Inserted resources appear.
- Updated current resources appear once with the latest content.
- Deleted current resources do not appear after deletion.
- History rows do not appear in `resources`.
- Hidden resources are excluded by default and included only when configured.

## SQL Generation

Use DuckDB's community extension:

```sql
INSTALL mongo FROM community;
LOAD mongo;
```

Use `mongo_scan(...)` for the view SQL because it accepts explicit database,
collection, filter, and sample-size arguments:

```sql
SELECT
  json_extract_string(resource_json, '$.id')::VARCHAR AS id,
  json_extract_string(resource_json, '$.resourceType')::VARCHAR AS resourceType,
  resource_json::JSON AS resource,
  patient_ref_expr::VARCHAR AS patient_ref
FROM (
  SELECT
    json_merge_patch(
      to_json(src)::JSON,
      '{"_id":null,"_uuid":null,"_sourceId":null,"_sourceAssigningAuthority":null}'::JSON
    ) AS resource_json
  FROM mongo_scan(<uri>, <database>, <collection>, filter := <json_filter>, sample_size := <n>) AS src
) mounted
```

Exact SQL may vary after the engineer verifies DuckDB's struct alias behavior
for `to_json(src)`, but these constraints are mandatory:

- Use `quote_sql_literal()` for URI, database, collection, and JSON filter
  string literals.
- Use `quote_identifier()` only for DuckDB identifiers such as attachment names.
- Use `json.dumps()` to construct Mongo filter JSON.
- Do not hand-build JSON filter strings.
- Use `json_merge_patch(..., {"field": null})` to remove only known server
  private fields. Do not strip every top-level key beginning with `_` because
  FHIR primitive extension fields may legitimately begin with `_`.
- Use configured `patient_reference_paths` through quoted SQL literals.
- Apply `resource_path`, `id_path`, and `resource_type_path` in generated SQL so
  both root-document and wrapped-document layouts project the same standard view.
- Local patient references are the only values converted to raw patient ids.
  Accept `Patient/<id>` and absolute URLs ending in `/Patient/<id>` only when
  the regex proves the final path segment is a Patient reference.

Schema-inference rule:

- The engineer must first verify that `sample_size := -1` is accepted by the
  installed DuckDB Mongo extension and scans enough documents to preserve sparse
  fields in `to_json(src)`.
- If `sample_size := -1` is accepted, keep it as the default.
- If it is rejected or does not preserve sparse fields, make `sample_size`
  explicit in the constructor and raise a clear error when correctness cannot be
  proven.

## Error Handling and Redaction

Add a private `_redact_mongo_uri()` helper.

It must mask:

- username
- password
- auth tokens in query parameters
- obvious credential parameters such as `authMechanismProperties`,
  `tlsCertificateKeyFilePassword`, `AWS_SESSION_TOKEN`, and variants

Errors should be actionable, for example:

- The DuckDB `mongo` extension could not be installed or loaded.
- Collection discovery failed and explicit resource types are required.
- A configured collection is absent or returns no compatible rows.
- The resulting view failed the standard resources schema validation.

Never include the raw Mongo URI in an exception message.

## Docker Deliverables

Create `docker/mongo-fhir-server/`.

Required files:

- `docker-compose.yml`
- `README.md`
- `Dockerfile.worker` if the worker/smoke profile is added
- example config for the source adapter
- example config for the Mongo materialization worker
- smoke script under `scripts/mongo/` or a local script in the Docker folder

Compose design:

- Default profile: MongoDB only, pinned to an explicit image tag. Start from
  `mongo:8.0.15` because upstream currently uses that tag. Run the local Mongo
  as a single-node replica set so change streams are available.
- Adapter smoke profile: seed a tiny R4 fixture directly through `mongosh` or a
  helper container, then run FHIR4DS against Mongo.
- Full Helix profile: run `icanbwell/fhir-server` only after a practical image
  or source-build flow is verified.
- Optional companion profiles for Keycloak, Redis, Kafka, and ClickHouse only if
  the full Helix smoke requires them.

Do not make the full upstream stack mandatory for the minimum adapter smoke.

## Documentation Deliverables

Repository docs:

- `docs/mongo-fhir-server.md`
- `docker/mongo-fhir-server/README.md`
- update `fhir4ds/sources/README.md`
- update `fhir4ds/sources/AGENTS.md` with the Mongo adapter invariants

Website docs:

- `web/website/docs/integrations/mongo-fhir-server.md`
- `web/website/docs/user-guide/sources/mongo-fhir-server.md`
- `web/website/docs/api-reference/sources/mongo-fhir-server.md`
- update `web/website/sidebars.ts`

Public exports:

- update `fhir4ds/sources/__init__.py`
- update API docs and examples

## Implementation Steps

1. Add the schema dataclass and adapter skeleton in
   `fhir4ds/sources/mongo_fhir.py`.
2. Add constructor validation and URI redaction helper.
3. Add JSON filter construction with `json.dumps`.
4. Add collection resolution for `per_resource`, `explicit`, and `shared`
   strategies, including full `MongoResourceCollection` layout mappings and
   shorthand `collection_mappings`.
5. Add SQL generation helpers:
   - extension install/load SQL
   - per-collection `mongo_scan` select
   - hidden-resource filter
   - current/deleted filter composition
   - resource/id/resourceType JSON path projection
   - private-field scrub patch
   - patient reference extraction expression
6. Add `register()` and `unregister()` with standard schema validation.
7. Export the adapter from `fhir4ds.sources`.
8. Add unit tests.
9. Add Mongo integration tests guarded for Docker/Mongo/extension availability.
10. Add Docker workflow and smoke script.
11. Add repository and website docs.
12. Run focused validation and then release/artifact gates if metadata, docs
    navigation, Docker, optional dependencies, or package exports changed.

## Test Plan

Unit tests in `fhir4ds/sources/tests/unit/test_mongo_fhir.py`:

- rejects non-string and empty constructor inputs
- validates mutually exclusive collection strategy options
- validates explicit `MongoResourceCollection` mappings
- validates custom `resource_path`, `id_path`, and `resource_type_path`
- builds safe `mongo_scan` SQL for simple per-resource mapping
- builds safe `mongo_scan` SQL for custom collection names and wrapped FHIR
  resource documents
- quotes URI, database, collection, and JSON filters as SQL literals
- quotes attachment names only as identifiers
- does not leak raw credentials in wrapped errors
- escapes malicious URI/database/collection/resource type/patient path inputs
- produces the exact `resources` schema for a fake or local DuckDB relation
- `register()` is idempotent
- `unregister()` is safe before `register()`
- `supports_incremental()` is false
- patient references are extracted from local `Patient/<id>` references
- absolute Patient URLs are normalized only when the final path proves Patient
- non-Patient references and external non-Patient URLs return NULL
- hidden tag filter is present by default and absent with `include_hidden=True`
- current and deleted filters compose with hidden/resourceType filters through
  JSON generated by `json.dumps`
- private-field scrub removes only configured private fields

Integration tests in `fhir4ds/sources/tests/integration/test_mongo_fhir.py`:

- skip only when Docker, MongoDB, or DuckDB community extension installation is
  unavailable
- `INSTALL mongo FROM community; LOAD mongo;` succeeds
- `mongo_scan` reads seeded Patient and Observation collections
- `sample_size := -1` preserves sparse fields, or the test documents the
  unsupported extension behavior and expects a clear adapter error
- `resources` exposes `id`, `resourceType`, `resource`, and `patient_ref`
- FHIRPath smoke runs against `resources`
- CQL/DQM smoke runs against a tiny patient fixture
- deleted/current semantics smoke proves current rows only when full Helix is
  available

Docker smoke:

- `docker compose up -d mongo`
- seed Patient and Observation
- run source adapter smoke
- run FHIRPath smoke
- run DQM/CQL smoke
- `docker compose down -v`

Docs validation:

- website build if website docs or sidebar changes
- docs links checked where existing scripts support it

Release/artifact gate:

- Required before final completion because this feature may affect package
  exports, optional dependencies, Docker artifacts, website navigation, and
  extension behavior.

## Acceptance Criteria

- `MongoFhirServerSource` registers a valid standard `resources` view.
- Runtime reads use DuckDB Mongo extension only.
- No Mongo writes occur from the adapter.
- Helix per-resource current collections are supported.
- Explicit collection mappings are supported.
- Explicit per-resource layout mappings are supported, including custom
  collection names, wrapped FHIR resource paths, and configured current/deleted
  filters.
- Shared collection mode is supported when `shared_collection` and
  `resource_types` are supplied.
- History, audit, and access-log collections are excluded by default.
- Hidden resources follow the configured include/exclude policy.
- Patient attribution matches the source adapter contract.
- SQL injection tests cover every dynamic SQL boundary.
- Credentials are redacted in errors and docs examples.
- Environment-gated integration tests and Docker smoke document skipped
  prerequisites clearly.
- Existing FHIRPath, CQL, ViewDefinition, and DQM code paths do not require
  source-specific branches.

## Open Questions for Implementation

- Does the installed DuckDB Mongo extension expose reliable catalog metadata for
  collection discovery through `ATTACH`? If not, require explicit
  `resource_types`, `collections`, or `collection_mappings`.
- Does `mongo_scan(..., sample_size := -1)` preserve sparse nested fields across
  the target DuckDB version and extension build? If not, the adapter must fail
  clearly unless a user-provided sample size is accepted as a conscious tradeoff.
- Is a pinned published Helix image usable for the full server smoke, or should
  the Docker workflow build from source by default?
