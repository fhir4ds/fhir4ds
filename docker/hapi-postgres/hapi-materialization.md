# HAPI PostgreSQL DQM Materialization

FHIR4DS can run DQM measures directly against a HAPI FHIR server that uses a
PostgreSQL backend. The PostgreSQL side provides durable patient-change queue
and result tables; PostgreSQL `LISTEN/NOTIFY` is used only as a wake-up signal
for online workers.

## Local Smoke Stack

Start the local HAPI/PostgreSQL stack:

```bash
docker compose -f docker/hapi-postgres/docker-compose.yml up -d postgres hapi
```

Install the materialization tables, decoded HAPI resource view, and triggers:

```bash
fhir4ds dqm hapi install \
  --config docker/hapi-postgres/hapi-materialization.example.yaml
```

Sync measure configuration:

```bash
fhir4ds dqm hapi sync-config \
  --config docker/hapi-postgres/hapi-materialization.example.yaml
```

Process one queue batch:

```bash
fhir4ds dqm hapi process-queue \
  --config docker/hapi-postgres/hapi-materialization.example.yaml \
  --limit 100
```

Queue current Patient resources for an initial run or controlled re-run:

```bash
fhir4ds dqm hapi enqueue-patients \
  --config docker/hapi-postgres/hapi-materialization.example.yaml \
  --all \
  --limit 25
```

Run as a long-lived worker:

```bash
fhir4ds dqm hapi listen \
  --config docker/hapi-postgres/hapi-materialization.example.yaml
```

Check queue, recent runs, active results, and published MeasureReports:

```bash
fhir4ds dqm hapi status \
  --config docker/hapi-postgres/hapi-materialization.example.yaml
```

For a staged non-production workflow, see `docs/hapi-pilot-runbook.md`.

## Artifact Sources

`artifacts.source: files` resolves Measure and CQL artifacts from the local
filesystem. Configure measure JSON, CQL library paths, include directories, and
ValueSet paths in the config.

`artifacts.source: hapi` resolves Measure, Library, and ValueSet artifacts from
`hapi.base_url`. Each measure should set `artifact_ref` to a Measure id,
`Measure/<id>`, or canonical URL. Referenced Library resources must contain a
`text/cql` or `application/cql` attachment. Referenced ValueSets must contain
an `expansion`, direct `compose.include.concept` codes, or be expandable by HAPI
`$expand`. If an unversioned CQL ValueSet declaration matches multiple HAPI
resources, FHIR4DS tries candidate versions newest-first and uses the newest
loadable or expandable ValueSet. Set `hapi.valueset_version_policy: error` to
require CQL `version` qualifiers or `canonical|version` references.

See:

- `docker/hapi-postgres/hapi-materialization.example.yaml`
- `docker/hapi-postgres/hapi-materialization.hapi-artifacts.example.yaml`
- `docker/hapi-postgres/hapi-materialization.external.example.yaml`
- `docs/dqm-artifact-resolvers.md`

## Result Tables

`fhir4ds_measure_result` stores the current active result per patient and
measure. When a patient is recalculated, the previous active row is inactivated
and a new row is inserted.

`fhir4ds_measure_audit` stores full audit JSON when `persist_audit` is enabled.

`fhir4ds_measure_report` stores generated individual MeasureReport resources
when `persist_measure_report` or `publish_measure_report_to_hapi` is enabled.
Publishing uses deterministic `PUT /MeasureReport/{id}` resource ids, making
worker retries idempotent.

## Hosted-Artifact Smoke

This script loads 2025 eCQM test patients and artifacts, resolves Measure,
Library, and ValueSet resources from HAPI, persists results, and publishes
individual MeasureReports back to HAPI:

```bash
python3 scripts/hapi/smoke_2025_materialization.py \
  --measure CMS117,CMS1218,CMS1017,CMS0334 \
  --limit-patients 1 \
  --max-process-loops 12 \
  --batch-size 25 \
  --artifact-source hapi \
  --publish-measure-report-to-hapi
```

If the local containers are already running under a different Compose session,
add `--skip-compose`.

## Retention

Use the configured retention policy to prune inactive result rows, audit rows,
and old run rows:

```bash
fhir4ds dqm hapi prune \
  --config docker/hapi-postgres/hapi-materialization.example.yaml
```

`status` is read-only and does not print connection strings or credentials:

```bash
fhir4ds dqm hapi status \
  --config docker/hapi-postgres/hapi-materialization.example.yaml \
  --limit 10
```

To manually retry failed queue rows:

```bash
fhir4ds dqm hapi reset-queue \
  --config docker/hapi-postgres/hapi-materialization.example.yaml \
  --all
```

To export patient-level materialized results for baseline comparison:

```bash
python3 scripts/hapi/export_materialization_results.py \
  --config docker/hapi-postgres/hapi-materialization.example.yaml \
  --format csv \
  --output hapi-results.csv
```
