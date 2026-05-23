---
id: cli
title: Command Line Interface
sidebar_label: CLI
---

# Command Line Interface

FHIR4DS installs a `fhir4ds` command for production-oriented workflows that are
better run from scripts, scheduled jobs, or CI than from notebooks.

```bash
fhir4ds --help
```

The current CLI surface focuses on Digital Quality Measure evaluation:

```bash
fhir4ds dqm --help
```

## DQM Commands

The `dqm` command group includes batch-evaluation commands and HAPI
materialization commands:

| Command | Purpose |
|---------|---------|
| `fhir4ds dqm validate` | Validate a DQM config before running it. |
| `fhir4ds dqm inspect` | Print a JSON summary of measures, libraries, valuesets, source, outputs, and audit settings. |
| `fhir4ds dqm run` | Evaluate configured measures and write output artifacts. |
| `fhir4ds dqm hapi install` | Install HAPI PostgreSQL queue/result tables and triggers. |
| `fhir4ds dqm hapi sync-config` | Sync materialized measure config into PostgreSQL. |
| `fhir4ds dqm hapi process-queue` | Process one batch of queued HAPI patient changes. |
| `fhir4ds dqm hapi listen` | Listen for HAPI change notifications and process continuously. |

Use the config-file workflow for repeatable production jobs:

```bash
fhir4ds dqm validate --config dqm-run.json
fhir4ds dqm inspect --config dqm-run.json
fhir4ds dqm run --config dqm-run.json
```

For a one-off single-measure run, use flags:

```bash
fhir4ds dqm run \
  --measure ./measures/Measure-CMS124.json \
  --cql ./cql/CMS124FHIR.cql \
  --library-dir ./cql \
  --source "./data/*.ndjson" \
  --source-type filesystem \
  --source-format ndjson \
  --valuesets ./valuesets \
  --period 2025-01-01:2025-12-31 \
  --audit-mode population \
  --measure-reports both \
  --definitions all \
  --definition-format json \
  --output ./dqm-output
```

## Inputs

The flag-based workflow supports these source types:

| Source Type | Use Case |
|-------------|----------|
| `filesystem` | FileSystemSource-compatible local or cloud paths. Supports formats such as `ndjson`, `json`, and `parquet`. |
| `directory` | Load a local directory of FHIR JSON resources with `FHIRDataLoader`. |
| `ndjson` | Load a single NDJSON file or directory of NDJSON files. |
| `json` | Load a single JSON file or directory of JSON files. |

Config files support the same DQM batch source types. For source adapters that
need application-managed setup, such as `ExistingTableSource` or
`PostgresSource`, use the Python API.

## Outputs

`fhir4ds dqm run` writes a root `run.json` and one directory per measure.
Depending on the output config, each measure directory can include:

| Output | Description |
|--------|-------------|
| `results.<format>` | Patient-level population results in JSON, CSV, or Parquet. |
| `summary.json` | Aggregate population counts, rate, and stratifier summaries. |
| `MeasureReport-summary.json` | FHIR summary MeasureReport. |
| `individual-reports/<patient>.json` | FHIR individual MeasureReport resources. |
| `definitions.<format>` | Machine-friendly CQL define outputs. |
| `definitions.schema.json` | Mapping from output columns to authored CQL define names. |

For full output details, see [Digital Quality Measures](./quality/dqm) and
[Source-to-DQM Production Recipes](./quality/dqm-recipes).

## HAPI Materialization

HAPI PostgreSQL materialization commands require the optional `psycopg`
dependency:

```bash
python3 -m pip install "psycopg[binary]>=3.1"
```

Then install schema objects and run the worker:

```bash
fhir4ds dqm hapi install \
  --connection postgresql://hapi:hapi@localhost:15432/hapi

fhir4ds dqm hapi sync-config --config hapi-dqm.yaml
fhir4ds dqm hapi process-queue --config hapi-dqm.yaml --limit 100
fhir4ds dqm hapi listen --config hapi-dqm.yaml
```

See [HAPI DQM Materialization](./quality/hapi-materialization) for table
layout, trigger behavior, and result persistence details.

## Audit Modes

| Mode | Use For |
|------|---------|
| `none` | Fast scoring and summary reports. |
| `population` | Routine review, resource-level evidence, and individual MeasureReports. |
| `full` | Deep CQL/debugging workflows that need expression-level traceability. |

Narratives require audit mode:

```bash
fhir4ds dqm run --config dqm-run.json --audit-mode population --narratives
```

When using a config file, prefer setting audit behavior in the config so
scheduled runs are fully reproducible.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Command succeeded. |
| `1` | Validation failed or one or more measures failed during a completed batch run. |
| `2` | Command-line or config input was invalid. |

## CI Usage

The CLI is suitable for automated checks:

```bash
fhir4ds dqm validate --config dqm-run.json
fhir4ds dqm run --config dqm-run.json
```

For performance-sensitive jobs, capture the root `run.json` and per-measure
`summary.json` files as CI artifacts. For spec conformance and timing reports in
this repository, use the conformance scripts under `conformance/scripts/`.
