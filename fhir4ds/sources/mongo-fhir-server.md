# Mongo FHIR Server Source

`MongoFhirServerSource` mounts current FHIR resources from a Mongo-backed FHIR
server as the standard FHIR4DS `resources` view. It uses DuckDB's community
`mongo` extension and `mongo_scan`, so analytics remain read-only and do not
copy PHI into a local DuckDB table.

## Default Layout

The default schema matches the Helix/icanbwell current-resource convention:

- Mongo database: `fhir`
- Collection names: `{ResourceType}_4_0_0`, such as `Patient_4_0_0`
- FHIR resource JSON stored as the root Mongo document
- Hidden resources excluded by the Helix hidden-tag convention

```python
import fhir4ds
from fhir4ds.sources import MongoFhirServerSchema, MongoFhirServerSource

source = MongoFhirServerSource(
    "mongodb://readonly:secret@mongo.example.org:27017",
    schema=MongoFhirServerSchema(
        database_name="fhir",
        resource_types=("Patient", "Observation", "Encounter"),
    ),
)

con = fhir4ds.create_connection(source=source)
```

## Configurable Collection Layouts

Use `collection_mappings` for custom per-resource collection names:

```python
schema = MongoFhirServerSchema(
    database_name="clinical",
    collection_strategy="explicit",
    collection_mappings={
        "Patient": "patients_current",
        "Observation": "observations_current",
    },
)
```

Use full `MongoResourceCollection` entries when the FHIR resource is wrapped in
another Mongo document:

```python
from fhir4ds.sources import MongoResourceCollection

schema = MongoFhirServerSchema(
    database_name="clinical",
    collection_strategy="explicit",
    collections=(
        MongoResourceCollection(
            resource_type="Observation",
            collection_name="observations_current",
            resource_path="$.payload.resource",
            id_path="$.payload.resource.id",
            resource_type_path="$.payload.resource.resourceType",
            current_filter={"tenant": "blue"},
            deleted_filter={"deleted": True},
        ),
    ),
)
```

Use `collection_strategy="shared"` when multiple resource types live in one
collection:

```python
schema = MongoFhirServerSchema(
    database_name="clinical",
    collection_strategy="shared",
    shared_collection="resources_current",
    shared_resource_path="$.resource",
    shared_id_path="$.resource.id",
    shared_resource_type_path="$.resource.resourceType",
    resource_types=("Patient", "Observation"),
)
```

## Filters

The adapter always adds a resource-type filter for configured resource types.
Additional filters are expressed as Mongo filter documents and serialized with
`json.dumps` before being passed to `mongo_scan`.

- `current_filter` adds an inclusion filter.
- `deleted_filter` is wrapped in `$nor`.
- Hidden-tag filtering is enabled by default and can be disabled with
  `include_hidden=True`.

## Patient Attribution

`patient_ref` is emitted as a raw Patient ID. Patient resources use their own
`id`; other resources check these default references:

- `subject.reference`
- `patient.reference`
- `beneficiary.reference`

Local `Patient/<id>` and absolute `http(s)://.../Patient/<id>` references are
normalized to `<id>`. Add paths with `patient_reference_paths` for custom
patient-bearing resources.

## Smoke Test

Run the local disposable Mongo stack:

```bash
cd docker/mongo-fhir-server
docker compose --profile smoke up --build worker
```

Or point the smoke script at an existing test database:

```bash
python3 scripts/mongo/smoke_mongo_source.py \
  --uri mongodb://localhost:27018 \
  --database fhir \
  --include-hidden
```

## Operational Notes

Use a read-only Mongo user or a read replica for production analytics. Large CQL
or DQM workloads can scan many current-resource documents, so run them away from
latency-sensitive transactional traffic when possible.

The materialization worker defaults to patient-scoped source reads. For each
claimed queue batch it recreates DuckDB's `resources` view with Mongo
`mongo_scan(filter := ...)` documents that restrict Patient resources by `id`
and patient-bearing resources by configured Patient reference paths. Disable
with `worker.source_patient_pushdown: false` only for troubleshooting.

`MongoFhirServerSource.supports_incremental()` returns `False` because the
source adapter is intentionally read-only.

For HAPI-like materialization parity, use the separate Mongo DQM worker:

```bash
fhir4ds dqm mongo install --config mongo-materialization.yaml
fhir4ds dqm mongo sync-config --config mongo-materialization.yaml
fhir4ds dqm mongo enqueue-patients --config mongo-materialization.yaml --all
fhir4ds dqm mongo process-queue --config mongo-materialization.yaml
```

The worker stores its own queue, run, result, audit, and generated
`MeasureReport` documents in Mongo collections. When
`publish_measure_report_to_mongo` is enabled, generated individual
`MeasureReport` resources are tagged and upserted back into the configured FHIR
resource collection.

Mongo does not have installable in-database triggers equivalent to PostgreSQL
triggers. The parity mechanism is a Mongo change stream:

```bash
fhir4ds dqm mongo listen --config mongo-materialization.yaml
```

Change streams require a replica set or sharded cluster. Delete events only
contain enough information to requeue non-Patient resources when pre-images are
available; enable MongoDB change stream pre-images if delete attribution matters
for your deployment.
