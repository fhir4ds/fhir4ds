---
id: dqm
title: Digital Quality Measures (DQM)
sidebar_label: DQM
---

# Digital Quality Measures (DQM)

The `fhir4ds.dqm` module evaluates FHIR `Measure` resources with their CQL logic
against a DuckDB-backed FHIR `resources` view. It is designed for production
batch runs as well as Python workflows: load source data, load terminology,
evaluate one or more measures, and write patient-level results plus FHIR
`MeasureReport` resources.

## 1. Evaluation Workflow

Most DQM runs follow the same shape:

1. Load FHIR resources into the standard `resources` view.
2. Load expanded ValueSets used by the measure libraries.
3. Parse each FHIR `Measure` and resolve its referenced CQL library.
4. Translate CQL populations to vectorized DuckDB SQL.
5. Write tabular results, summaries, optional definition outputs, and optional
   FHIR `MeasureReport` resources.

For production jobs, prefer the CLI batch runner. For notebooks, tests, and
custom applications, use `MeasureEvaluator` directly.

## 2. CLI Batch Runner

The CLI exposes three DQM subcommands:

```bash
fhir4ds dqm validate --config dqm-run.json
fhir4ds dqm inspect --config dqm-run.json
fhir4ds dqm run --config dqm-run.json
```

`validate` checks paths and required configuration. `inspect` prints the
measures, libraries, valuesets, outputs, and audit settings that will be used.
`run` evaluates the configured measures and writes one output directory per
measure.

### Config File

```json
{
  "measures": [
    {
      "id": "CMS124",
      "path": "./measures/Measure-CMS124.json",
      "cql": "./cql/CMS124FHIR.cql"
    }
  ],
  "libraries": {
    "paths": ["./cql"]
  },
  "source": {
    "type": "filesystem",
    "path": "./bulk-export/**/*.ndjson",
    "format": "ndjson"
  },
  "terminology": {
    "valuesets": ["./valuesets"]
  },
  "period": {
    "start": "2025-01-01",
    "end": "2025-12-31"
  },
  "audit": {
    "mode": "population",
    "narratives": false
  },
  "outputs": {
    "directory": "./dqm-output",
    "formats": ["json", "parquet"],
    "measure_reports": "both",
    "definitions": {
      "mode": "all",
      "formats": ["json"],
      "include_sde": false
    }
  },
  "continue_on_error": true
}
```

### CLI-Only Run

For a single measure, the same run can be launched without a config file:

```bash
fhir4ds dqm run \
  --measure ./measures/Measure-CMS124.json \
  --cql ./cql/CMS124FHIR.cql \
  --library-dir ./cql \
  --source "./bulk-export/**/*.ndjson" \
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

## 3. Outputs

Each successful measure run writes a directory named from the measure id:

```text
dqm-output/
  run.json
  CMS124/
    results.json
    results.parquet
    summary.json
    MeasureReport-summary.json
    definitions.json
    definitions.schema.json
    individual-reports/
      patient-1.json
      patient-2.json
```

### Tabular Results

`results.<format>` contains one row per evaluated patient or population-basis
record. It always includes `patient_id` and population columns such as
`initial_population`, `denominator`, `numerator`, and exclusion/exception
columns when they are present in the measure.

When audit is enabled, population columns contain audit structs rather than bare
booleans. The struct has a `result` value and an `evidence` list. CSV output
serializes dict/list cells as JSON strings.

### Summary

`summary.json` contains aggregate population counts, denominator/numerator final
counts, performance rate, and stratifier summaries when the Measure defines
stratifiers.

### Definition Outputs

`outputs.definitions` writes CQL define statements as machine-readable per-patient
columns. Use this when downstream systems need more than final population
membership.

Supported modes:

| Mode | Behavior |
|------|----------|
| `none` | Do not write definition outputs. |
| `all` | Write every define in the primary CQL library, excluding `SDE*` by default. |
| `selected` | Write only the names listed in `outputs.definitions.names`. |

`definitions.schema.json` maps output column names back to authored CQL define
names. This is important because output columns are normalized to SQL-safe names.

## 4. MeasureReport Resources

Set `outputs.measure_reports` to control FHIR `MeasureReport` output:

| Mode | Output |
|------|--------|
| `none` | No MeasureReport resources. |
| `summary` | One aggregate `MeasureReport-summary.json` per measure. |
| `individual` | One individual report per patient in `individual-reports/`. |
| `both` | Write summary and individual reports. |

Summary reports include the computed performance rate extension:

```json
{
  "url": "http://hl7.org/fhir/us/davinci-deqm/StructureDefinition/performanceRate",
  "valueDecimal": 0.84
}
```

Individual reports use the Da Vinci DEQM individual MeasureReport profile:

```json
{
  "resourceType": "MeasureReport",
  "type": "individual",
  "meta": {
    "profile": [
      "http://hl7.org/fhir/us/davinci-deqm/StructureDefinition/indv-measurereport-deqm"
    ]
  },
  "subject": {
    "reference": "Patient/patient-1"
  }
}
```

The engine preserves authored Measure group and population ids in the
`MeasureReport` when present. It also adds R5 backport linkId extensions so
consumers can correlate report groups/populations with the source `Measure`.

## 5. Supporting Evidence

FHIR4DS reads Measure-authored `cqf-supportingEvidenceDefinition` references on
population criteria and can serialize the corresponding values into individual
reports using `cqf-supportingEvidence`.

The extension is attached to the relevant
`MeasureReport.group.population.extension` entry. Each supporting evidence item
contains:

- `name`: the referenced CQL expression name.
- `description`: if provided by the Measure.
- `code`: if provided by the Measure.
- `value`: the evaluated CQL result for the individual patient.

Example:

```json
{
  "url": "http://hl7.org/fhir/StructureDefinition/cqf-supportingEvidence",
  "extension": [
    {
      "url": "name",
      "valueCode": "Most Recent Blood Pressure"
    },
    {
      "url": "value",
      "valueReference": {
        "reference": "Observation/bp-1"
      }
    }
  ]
}
```

Supporting evidence is gathered during the primary measure evaluation when
individual reports are requested. It does not require a second evidence-only
evaluation. If audit mode wraps a value as `{result, evidence}`, only `result` is
serialized into the MeasureReport extension; internal audit trace details remain
in the tabular audit output.

## 6. Audit Modes

Audit mode controls how much evidence is captured in `results.<format>`:

| Mode | Use For | Cost |
|------|---------|------|
| `none` | Fast production scoring and summary reports. | Lowest |
| `population` | Routine review, individual reports, and resource-level evidence. | Moderate |
| `full` | Deep debugging of CQL logic and expression-level traceability. | Highest |

Narratives require audit mode and add human-readable text to audit structs. Use
them for review workflows, not default scoring jobs.

For routine batch output with individual MeasureReports, start with
`audit.mode = "population"`. Use `full` only when expression-level debugging is
needed.

## 7. Python API

```python
import fhir4ds
from fhir4ds.dqm import MeasureEvaluator, AuditMode
from fhir4ds.sources import FileSystemSource

con = fhir4ds.create_connection(
    source=FileSystemSource("./bulk-export/**/*.ndjson", format="ndjson")
)

evaluator = MeasureEvaluator(con)
result = evaluator.evaluate(
    measure_bundle="./measures/Measure-CMS124.json",
    cql_library_path="./cql/CMS124FHIR.cql",
    include_paths=["./cql"],
    parameters={"Measurement Period": ("2025-01-01", "2025-12-31")},
    audit_mode=AuditMode.POPULATION,
    include_supporting_evidence=True,
)

summary = evaluator.summary_report(result)
report = evaluator.to_measure_report(
    result,
    period_start="2025-01-01",
    period_end="2025-12-31",
    report_type="summary",
)
```

See the [DQM API Reference](/docs/api-reference/dqm/) for the full Python and
batch configuration surface.
