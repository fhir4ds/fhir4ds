---
title: HAPI DQM Materialization
sidebar_label: HAPI Materialization
---

# HAPI DQM Materialization

FHIR4DS can keep patient-level DQM results materialized from a HAPI FHIR JPA
Server PostgreSQL backend.

The design separates change capture from measure calculation:

```text
HAPI PostgreSQL trigger
  -> fhir4ds_patient_change_queue
  -> pg_notify('fhir4ds_patient_changed', ...)
  -> FHIR4DS worker
  -> fhir4ds_measure_result / fhir4ds_measure_audit
```

PostgreSQL triggers only enqueue changed patients. They do not run CQL or DQM
logic inside the HAPI write transaction.

## Install Tables and Triggers

Install the FHIR4DS-owned schema objects into the HAPI PostgreSQL database:

```bash
fhir4ds dqm hapi install \
  --connection postgresql://hapi:hapi@localhost:15432/hapi
```

This creates:

- `fhir4ds_patient_change_queue`
- `fhir4ds_measure_config`
- `fhir4ds_measure_run`
- `fhir4ds_measure_result`
- `fhir4ds_measure_audit`
- trigger functions on `hfj_resource` and `hfj_res_ver`

## Configure Measures

Use a YAML or JSON materialization config:

```yaml
postgres:
  connection_string: postgresql://hapi:hapi@localhost:15432/hapi

period:
  start: "2026-01-01"
  end: "2026-12-31"

defaults:
  audit_mode: population

results:
  persist_audit: true

measures:
  - id: CMS122
    enabled: true
    path: /data/ecqm/Measure-CMS122.json
    cql: /data/ecqm/CMS122.cql
    version: "2025"
```

Sync the config into PostgreSQL:

```bash
fhir4ds dqm hapi sync-config --config hapi-dqm.yaml
```

The worker reads enabled rows from `fhir4ds_measure_config`. A config file may
also carry measure definitions directly for local one-off runs.

## Process Changes

Process one batch:

```bash
fhir4ds dqm hapi process-queue --config hapi-dqm.yaml --limit 100
```

Run continuously with `LISTEN/NOTIFY` and polling fallback:

```bash
fhir4ds dqm hapi listen --config hapi-dqm.yaml
```

The durable queue is the source of truth. Notifications are wake-up messages
only; if the worker is offline, pending rows remain in the queue.

## Result Storage

`fhir4ds_measure_result` is the indexed current/history table. Recalculation
deactivates the previous active row for `(patient_id, measure_id)` and inserts a
new row.

Full audit is stored separately in `fhir4ds_measure_audit` when
`persist_audit` is enabled. This keeps current-result queries small while
retaining evidence for later review.

## Current Scope

This integration currently supports HAPI current resources stored inline as
JSON in `hfj_res_ver.res_text_vc`. Compressed `JSONC` resource bodies are
detected by `HapiPostgresSource` and remain a later enhancement.

## 2025 eCQM Smoke Testing

Use the repository's 2025 conformance fixture to load selected test patients
into the local HAPI server:

```bash
python3 scripts/hapi/load_2025_measure.py \
  --measure CMS122 \
  --base-url http://localhost:18080/fhir \
  --limit-patients 1
```

The script prints a suggested `measures[]` config entry with the discovered
Measure bundle, CQL file, include paths, and ValueSet paths. Start with one
measure and one patient, then expand the patient limit and measure set after the
queue/result workflow is behaving as expected.
