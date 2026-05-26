---
id: mongo-fhir-server
title: Connecting to Mongo FHIR Servers
sidebar_label: Mongo FHIR Server
---

# Connecting to Mongo FHIR Servers

`MongoFhirServerSource` lets FHIR4DS query a Mongo-backed FHIR server in place
through DuckDB's community `mongo` extension.

The adapter is read-only. It creates the standard `resources` view from current
FHIR resource collections without copying data into DuckDB.

## Default Helix/icanbwell Layout

The default layout expects one current-resource collection per FHIR resource
type:

- `Patient_4_0_0`
- `Observation_4_0_0`
- `Encounter_4_0_0`

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

## Custom Collection Names

Use `collection_strategy="explicit"` when your Mongo collections do not follow
the `{ResourceType}_4_0_0` naming convention:

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

## Wrapped Resource Documents

If the FHIR resource is nested inside another Mongo document, configure paths
with `MongoResourceCollection`:

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

## Shared Collection Layout

Use `collection_strategy="shared"` when all current resources live in one
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

## Patient Attribution

The adapter emits `patient_ref` as a raw Patient ID:

- `Patient` resources use their own `id`.
- Other resources check `subject.reference`, `patient.reference`, and
  `beneficiary.reference` by default.
- `Patient/<id>` and absolute `http(s)://.../Patient/<id>` references are
  normalized to `<id>`.

Add `patient_reference_paths` when your data uses other patient-bearing fields.

## Hidden and Deleted Resources

Hidden resources are excluded by default using the Helix hidden-tag convention.
Set `include_hidden=True` for audits or source debugging.

`deleted_filter` is wrapped in `$nor`, while `current_filter` is added as an
ordinary Mongo filter document. Filters are passed to `mongo_scan`, so they can
reduce documents read from Mongo.

## Local Smoke Test

```bash
cd docker/mongo-fhir-server
docker compose --profile smoke up --build worker
```

Or run the Python smoke against an existing Mongo test database:

```bash
python3 scripts/mongo/smoke_mongo_source.py \
  --uri 'mongodb://localhost:27018/?directConnection=true' \
  --database fhir \
  --include-hidden
```

## DQM Materialization

For HAPI-like materialization, use the Mongo DQM worker instead of the read-only
source adapter:

```bash
fhir4ds dqm mongo install --config mongo-materialization.yaml
fhir4ds dqm mongo sync-config --config mongo-materialization.yaml
fhir4ds dqm mongo enqueue-patients --config mongo-materialization.yaml --all
fhir4ds dqm mongo listen --config mongo-materialization.yaml
```

The worker uses Mongo change streams for data-change wakeups and stores durable
queue/result/report documents in Mongo. Generated individual `MeasureReport`
resources can be upserted back into the configured Mongo FHIR resource
collection with `publish_measure_report_to_mongo: true`.

`worker.source_patient_pushdown` defaults to `true`, so claimed queue batches
also filter the Mongo source scans to the affected Patient IDs before CQL
execution.

Change streams require a Mongo replica set or sharded cluster. Enable pre-images
when delete events for non-Patient resources must preserve patient attribution.
