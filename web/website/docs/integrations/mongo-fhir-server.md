---
id: mongo-fhir-server
title: Mongo FHIR Server Integration
sidebar_label: Mongo FHIR Server
---

# Mongo FHIR Server Integration

`MongoFhirServerSource` connects FHIR4DS analytics to Mongo-backed FHIR servers,
including Helix/icanbwell-style deployments where current resources are stored
in per-resource Mongo collections.

## What It Does

The adapter:

- Loads DuckDB's community `mongo` extension.
- Reads Mongo collections through `mongo_scan`.
- Projects current FHIR resources into the FHIR4DS `resources` view.
- Normalizes Patient references for CQL and DQM evaluation.
- Keeps the source read-only from FHIR4DS.

## Recommended Deployment Pattern

Use a read-only Mongo user or a read replica for analytics workloads:

```python
from fhir4ds.sources import MongoFhirServerSchema, MongoFhirServerSource

source = MongoFhirServerSource(
    "mongodb://analytics_user:secret@mongo-replica.example.org:27017",
    schema=MongoFhirServerSchema(
        database_name="fhir",
        resource_types=("Patient", "Observation", "Encounter", "Condition"),
    ),
)
```

Large CQL and DQM runs can scan many current-resource documents. Keep them away
from latency-sensitive transactional traffic unless the Mongo deployment has
capacity reserved for analytics.

## Materialization Parity With HAPI

FHIR4DS also includes a Mongo DQM materialization worker for HAPI-like
operation:

- Durable patient-change queue in Mongo.
- Measure run, result, audit, and generated MeasureReport collections.
- Initial manual enqueue of current Patient resources.
- Change-stream listener for new or updated FHIR resources.
- Optional generated individual `MeasureReport` upsert back into Mongo.

```bash
fhir4ds dqm mongo install --config mongo-materialization.yaml
fhir4ds dqm mongo sync-config --config mongo-materialization.yaml
fhir4ds dqm mongo enqueue-patients --config mongo-materialization.yaml --all
fhir4ds dqm mongo listen --config mongo-materialization.yaml
```

Mongo does not support installable in-database triggers equivalent to
PostgreSQL. The parity path uses Mongo change streams, so the Mongo deployment
must be a replica set or sharded cluster. Enable change stream pre-images if
delete events must requeue non-Patient resources by their prior patient
reference.

The worker defaults to `source_patient_pushdown: true`. For each claimed queue
batch it adds Patient ID filters to the Mongo source scans before DuckDB
evaluates the measure, so batch runs do not need to read every configured
resource collection.

## Layout Options

Choose the schema strategy that matches your server:

| Strategy | Use When |
|----------|----------|
| `per_resource` | Collections are named like `Patient_4_0_0`. |
| `explicit` | Each resource type has a custom collection name or wrapped JSON layout. |
| `shared` | Multiple resource types are stored in one shared collection. |

All strategies add a resource-type filter, so the mounted `resources` view only
includes configured resource types.

## Local Test Stack

The repository includes a disposable Mongo stack:

```bash
cd docker/mongo-fhir-server
docker compose --profile smoke up --build worker
```

This starts Mongo, seeds a Patient and Observation fixture, and runs
`scripts/mongo/smoke_mongo_source.py` through the packaged worker image.
The Mongo service runs as a single-node replica set so change streams are
available for materialization experiments.

To keep Mongo running for manual queries:

```bash
docker compose up -d mongo
docker compose --profile smoke run --rm seed
```

Then run:

```bash
python3 scripts/mongo/smoke_mongo_source.py \
  --uri 'mongodb://localhost:27018/?directConnection=true' \
  --database fhir \
  --include-hidden
```

## Current Limitations

`MongoFhirServerSource.supports_incremental()` returns `False`; incremental
behavior belongs to the separate DQM materialization worker, not the read-only
source adapter.

Collection discovery is best-effort. For production deployments, provide
`resource_types`, `collection_mappings`, or full `collections` configuration so
schema drift fails clearly at startup.
