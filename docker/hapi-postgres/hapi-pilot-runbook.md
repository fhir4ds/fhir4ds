# HAPI Materialization Pilot Runbook

This runbook is for controlled testing against a non-production HAPI FHIR server
using a PostgreSQL backend. It assumes FHIR4DS-owned tables, views, and triggers
can be installed in the HAPI database.

## Safety Boundaries

- Use a restored copy, staging database, or other non-production HAPI database.
- Start with one to three measures and a small patient cohort.
- Keep `results.publish_measure_report_to_hapi: false` until stored result rows
  and generated MeasureReport JSON have been reviewed.
- Prefer `defaults.audit_mode: population` for the first pass. Full audit can be
  much larger and should be enabled after row counts and performance are known.
- Do not run `enqueue-patients --all` until measure config, artifact resolution,
  and a limited patient sample have succeeded.

## Configure

Use the external example as the starting point:

```bash
cp docker/hapi-postgres/hapi-materialization.external.example.yaml hapi-pilot.yaml
```

Set connection and HAPI endpoint values through environment variables so secrets
do not need to live in the YAML file:

```bash
export FHIR4DS_HAPI_POSTGRES_URL='postgresql://user:password@host:5432/hapi'
export FHIR4DS_HAPI_BASE_URL='https://hapi.example/fhir'
export FHIR4DS_HAPI_BEARER_TOKEN='optional-token'
export FHIR4DS_ARTIFACT_DIR='/artifacts'
```

Config strings support `${NAME}` and `${NAME:-default}` interpolation.

For file-backed artifacts, mount or copy Measure, CQL Library, and ValueSet files
under `FHIR4DS_ARTIFACT_DIR`. For HAPI-backed artifacts, set:

```yaml
artifacts:
  source: hapi
measures:
  - id: CMS117
    artifact_source: hapi
    artifact_ref: CMS117FHIRChildhoodImmunizationStatus
```

## Install And Sync

Install the decoded HAPI resource view, queue/result tables, and triggers:

```bash
fhir4ds dqm hapi install --config hapi-pilot.yaml
```

Sync enabled measure configuration into PostgreSQL:

```bash
fhir4ds dqm hapi sync-config --config hapi-pilot.yaml
```

Check the operational summary:

```bash
fhir4ds dqm hapi status --config hapi-pilot.yaml --limit 10
```

## Seed A Pilot Cohort

Queue specific patients first:

```bash
fhir4ds dqm hapi enqueue-patients \
  --config hapi-pilot.yaml \
  --patient-id patient-1 \
  --patient-id patient-2
```

For a bounded sample from current Patient resources:

```bash
fhir4ds dqm hapi enqueue-patients \
  --config hapi-pilot.yaml \
  --all \
  --limit 25
```

Only after limited validation should the full current population be queued:

```bash
fhir4ds dqm hapi enqueue-patients --config hapi-pilot.yaml --all
```

Future HAPI writes are queued by PostgreSQL triggers after `install`.

## Process

Run one batch while watching logs:

```bash
fhir4ds dqm hapi process-queue \
  --config hapi-pilot.yaml \
  --limit 25 \
  --log-level INFO
```

Run continuously after the one-shot batch is stable:

```bash
fhir4ds dqm hapi listen --config hapi-pilot.yaml --log-level INFO
```

The worker uses the queue table as the durable contract. `LISTEN/NOTIFY` only
wakes online workers; polling still catches missed notifications.

## Export And Compare

Export active patient-level population rows:

```bash
python3 scripts/hapi/export_materialization_results.py \
  --config hapi-pilot.yaml \
  --format csv \
  --output pilot-results.csv
```

Compare against a baseline CSV or JSON file. By default the comparison key is
`measure_id,patient_id`; add repeated `--key` options if the baseline has
multiple rows per patient and measure.

```bash
python3 scripts/hapi/export_materialization_results.py \
  --config hapi-pilot.yaml \
  --expected expected-results.csv \
  --output pilot-comparison.json
```

The script exits with status `1` when deltas are found. Compare patient-level
population membership before relying on aggregate counts.

## Retry And Reset

Failed rows are retried automatically until `worker.max_attempts` is reached and
`worker.retry_backoff_seconds` has elapsed. To manually retry failed rows:

```bash
fhir4ds dqm hapi reset-queue --config hapi-pilot.yaml --all
fhir4ds dqm hapi process-queue --config hapi-pilot.yaml --limit 25
```

To reset specific patients:

```bash
fhir4ds dqm hapi reset-queue \
  --config hapi-pilot.yaml \
  --patient-id patient-1 \
  --status failed
```

Use `--status complete` only for deliberate re-runs of already completed
patients. Use `--status processing` only after confirming no worker is currently
processing those rows.

## Retention

After the pilot, prune old inactive result rows, audit rows, and unreferenced run
rows using the configured retention policy:

```bash
fhir4ds dqm hapi prune --config hapi-pilot.yaml
```

## What To Record

- HAPI version and Docker/image tag, if applicable.
- HAPI database size and patient count.
- Measure ids, artifact source, and ValueSet version policy.
- Queue depth before and after each run.
- Runtime per batch, errors, and slow measures from status/run rows.
- Result deltas against the baseline.
- Audit and MeasureReport storage growth.
