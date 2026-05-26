# Mongo FHIR Server Dev Stack

Disposable local stack for testing `MongoFhirServerSource`.

```bash
cd docker/mongo-fhir-server
docker compose up -d mongo
```

Endpoint:

- MongoDB: `mongodb://localhost:27018/?directConnection=true`

The local Mongo container runs as a single-node replica set so Mongo change
streams are available for materialization tests.

Seed the small FHIR fixture:

```bash
docker compose --profile smoke run --rm seed
```

Run the adapter smoke from the repository:

```bash
python3 scripts/mongo/smoke_mongo_source.py \
  --uri 'mongodb://localhost:27018/?directConnection=true' \
  --database fhir \
  --include-hidden
```

Or run the packaged worker smoke:

```bash
docker compose --profile smoke up --build worker
```

The fixture uses the default Helix/icanbwell current-resource convention:

- `Patient_4_0_0`
- `Observation_4_0_0`

`mongo-source.example.yaml` shows the equivalent source-adapter settings for
the local stack. It is documentation-only; instantiate
`MongoFhirServerSchema` with the same values in Python.

`mongo-materialization.example.yaml` shows the DQM worker settings for HAPI-like
parity: a durable patient-change queue, result/report collections, and generated
`MeasureReport` resources written back into Mongo.

Initialize materialization indexes and sync measure config:

```bash
fhir4ds dqm mongo install \
  --config docker/mongo-fhir-server/mongo-materialization.example.yaml

fhir4ds dqm mongo sync-config \
  --config docker/mongo-fhir-server/mongo-materialization.example.yaml
```

Queue an initial patient set and process once:

```bash
fhir4ds dqm mongo enqueue-patients \
  --config docker/mongo-fhir-server/mongo-materialization.example.yaml \
  --all \
  --limit 25

fhir4ds dqm mongo process-queue \
  --config docker/mongo-fhir-server/mongo-materialization.example.yaml
```

Run the change-stream worker:

```bash
fhir4ds dqm mongo listen \
  --config docker/mongo-fhir-server/mongo-materialization.example.yaml
```

Mongo does not support installable in-database triggers like PostgreSQL. The
Mongo parity path uses change streams, so production deployments must be a
replica set or sharded cluster and should enable pre-images if delete events
must requeue non-Patient resources by their prior patient reference.

The worker defaults to `source_patient_pushdown: true`. Each claimed queue batch
adds Patient ID filters to the Mongo source scans before CQL executes, reducing
documents read for batch materialization.

Use the script flags to verify custom layouts:

```bash
python3 scripts/mongo/smoke_mongo_source.py \
  --uri 'mongodb://localhost:27018/?directConnection=true' \
  --database fhir \
  --strategy explicit \
  --collection-map Patient=Patient_4_0_0 \
  --collection-map Observation=Observation_4_0_0
```

Cleanup:

```bash
docker compose down -v
```

The compose file defaults to `MONGO_IMAGE=mongo:8.0.15` and
`FHIR4DS_WORKER_PYTHON_IMAGE=python:3.11.13-slim`. Override those environment
variables when testing another verified image.
