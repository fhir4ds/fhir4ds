---
id: dqm
title: dqm
sidebar_label: dqm
---

# `fhir4ds.dqm`

Digital Quality Measure orchestration for FHIR `Measure` resources, CQL
libraries, audit evidence, batch runs, and FHIR `MeasureReport` output.

## Imports

```python
from fhir4ds.dqm import (
    MeasureEvaluator,
    AuditEngine,
    AuditMode,
    AuditOrStrategy,
)
from fhir4ds.dqm.config import (
    DQMRunConfig,
    MeasureSpec,
    SourceSpec,
    TerminologySpec,
    AuditSpec,
    OutputSpec,
    DefinitionOutputSpec,
    load_run_config,
    parse_run_config,
)
from fhir4ds.dqm.batch import (
    run_batch,
    validate_config,
    inspect_config,
)
```

## `MeasureEvaluator`

```python
MeasureEvaluator(
    conn,
    audit_or_strategy=AuditOrStrategy.TRUE_BRANCH,
    narrative_generator=None,
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `conn` | `duckdb.DuckDBPyConnection` | Connection containing the FHIR `resources` view and loaded terminology. |
| `audit_or_strategy` | `AuditOrStrategy` | Evidence collection strategy for CQL `or` expressions. |
| `narrative_generator` | `NarrativeGenerator | None` | Optional custom audit narrative generator. |

### `evaluate(...)`

```python
result = evaluator.evaluate(
    measure_bundle,
    cql_library_path,
    parameters=None,
    audit=False,
    audit_mode=AuditMode.NONE,
    filter_to_ip=False,
    patient_ids=None,
    include_paths=None,
    generate_narratives=False,
    include_supporting_evidence=False,
)
```

Evaluates a FHIR `Measure` against the connection's `resources` view.

| Parameter | Type | Description |
|-----------|------|-------------|
| `measure_bundle` | `str | Path | dict` | Path to Measure JSON or an already parsed Measure dict. |
| `cql_library_path` | `str | Path` | Main CQL library file for the Measure. |
| `parameters` | `dict | None` | CQL parameter overrides. Use `{"Measurement Period": (start, end)}` for MeasureReport period inference. |
| `audit` | `bool` | Backward-compatible shortcut for full audit when `audit_mode` is `none`. |
| `audit_mode` | `str | AuditMode` | `none`, `population`, or `full`. |
| `filter_to_ip` | `bool` | Return only rows meeting Initial Population. |
| `patient_ids` | `list[str] | None` | Restrict evaluation to selected patient ids. |
| `include_paths` | `list[str] | None` | Directories used to resolve included CQL libraries. |
| `generate_narratives` | `bool` | Add plain-English audit narratives. Requires audit mode. |
| `include_supporting_evidence` | `bool` | Add `evidence_*` columns for Measure-authored supporting evidence definitions. |

Returns a `MeasureResult`.

### `summary_report(result)`

```python
summary = evaluator.summary_report(result)
```

Returns aggregate counts, denominator/numerator final counts, performance rate,
and stratifier summaries when present.

### `to_csv(result, path)`

```python
evaluator.to_csv(result, "./results.csv")
```

Writes the result DataFrame to CSV. Dict/list cells, including audit structs,
are serialized as JSON strings.

### `to_measure_report(...)`

```python
report = evaluator.to_measure_report(
    result,
    period_start="2025-01-01",
    period_end="2025-12-31",
    status="complete",
    report_type="summary",
)
```

Creates a FHIR `MeasureReport` dict.

| Parameter | Type | Description |
|-----------|------|-------------|
| `result` | `MeasureResult | DataFrame` | Prefer the `MeasureResult` returned by `evaluate()`. |
| `period_start` | `str | date | None` | Measurement period start. |
| `period_end` | `str | date | None` | Measurement period end. |
| `status` | `str` | FHIR MeasureReport status. Defaults to `complete`. |
| `report_type` | `str` | `summary`, `individual`, or `subject-list`. |

For individual reports, `result.dataframe` must contain exactly one patient row.
Individual reports include the DEQM individual MeasureReport profile and a
`subject.reference`.

## `MeasureResult`

```python
@dataclass
class MeasureResult:
    dataframe: pandas.DataFrame
    populations: dict[str, Any]
    parameters: dict[str, Any]
    measure_url: str | None = None
    pop_map: PopulationMap | None = None
```

| Field | Description |
|-------|-------------|
| `dataframe` | Patient-level or population-basis evaluation output. |
| `populations` | Mapping of normalized population column names to CQL expressions. |
| `parameters` | Parameters used for evaluation. |
| `measure_url` | Measure library/canonical reference when available. |
| `pop_map` | Parsed Measure population map used by export methods. |

## Audit Types

### `AuditMode`

| Value | Description |
|-------|-------------|
| `AuditMode.NONE` / `"none"` | No audit wrapping. Fastest mode. |
| `AuditMode.POPULATION` / `"population"` | Captures retrieve/resource-level evidence for population outputs without wrapping every expression. |
| `AuditMode.FULL` / `"full"` | Wraps expressions with audit macros for expression-level traceability. |

### `AuditOrStrategy`

| Value | Description |
|-------|-------------|
| `AuditOrStrategy.TRUE_BRANCH` | Keep evidence from the branch that made the `or` true. |
| `AuditOrStrategy.ALL` | Keep evidence from all `or` branches. |

## Batch Runner

### `run_batch(config)`

```python
from fhir4ds.dqm.batch import run_batch
from fhir4ds.dqm.config import load_run_config

config = load_run_config("dqm-run.json")
batch_result = run_batch(config)
```

Executes all configured measures and writes outputs to
`config.outputs.directory`.

### `validate_config(config)`

Returns a list of validation errors. An empty list means the config is valid.

### `inspect_config(config)`

Returns a JSON-serializable description of referenced measures, libraries,
valuesets, output settings, and audit settings.

## Batch Config Dataclasses

### `DQMRunConfig`

```python
DQMRunConfig(
    measures,
    source,
    outputs,
    libraries=[],
    terminology=TerminologySpec(),
    parameters={},
    period_start=None,
    period_end=None,
    patient_ids=None,
    filter_to_ip=False,
    audit=AuditSpec(),
    continue_on_error=True,
)
```

### `MeasureSpec`

| Field | Description |
|-------|-------------|
| `path` | FHIR Measure JSON path. |
| `cql` | Optional explicit CQL file path. If omitted, the runner resolves from library paths. |
| `id` | Optional output id override. |

### `SourceSpec`

| Field | Description |
|-------|-------------|
| `type` | `filesystem`, `directory`, `ndjson`, or `json`. |
| `path` | Source path, glob, or cloud URI. |
| `format` | Filesystem format such as `ndjson`, `json`, or `parquet`. |
| `hive_partitioning` | Enable Hive partition discovery for filesystem sources. |

### `OutputSpec`

| Field | Description |
|-------|-------------|
| `directory` | Output directory. |
| `formats` | Result formats: `json`, `csv`, `parquet`. |
| `measure_reports` | `none`, `summary`, `individual`, or `both`. |
| `definitions` | `DefinitionOutputSpec`. |

### `DefinitionOutputSpec`

| Field | Description |
|-------|-------------|
| `mode` | `none`, `all`, or `selected`. |
| `formats` | Definition output formats: `json`, `csv`, `parquet`. |
| `include_sde` | Include `SDE*` definitions when `mode` is `all`. |
| `definitions` | Definition names when `mode` is `selected`. |

## Config File Schema

JSON and YAML config files are accepted by `load_run_config`.

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
    "format": "ndjson",
    "hive_partitioning": false
  },
  "terminology": {
    "valuesets": ["./valuesets"]
  },
  "period": {
    "start": "2025-01-01",
    "end": "2025-12-31"
  },
  "parameters": {},
  "patient_ids": ["patient-1"],
  "filter_to_ip": false,
  "audit": {
    "mode": "population",
    "narratives": false
  },
  "outputs": {
    "directory": "./dqm-output",
    "formats": ["json"],
    "measure_reports": "both",
    "definitions": {
      "mode": "selected",
      "formats": ["json"],
      "names": ["Initial Population", "Numerator"],
      "include_sde": false
    }
  },
  "continue_on_error": true
}
```

## CLI

```bash
fhir4ds dqm validate --config dqm-run.json
fhir4ds dqm inspect --config dqm-run.json
fhir4ds dqm run --config dqm-run.json
```

Common `run` options:

| Option | Description |
|--------|-------------|
| `--measure` | Measure JSON path. May be repeated. |
| `--cql` | CQL path matching `--measure`. May be repeated. |
| `--library-dir` | Directory for included CQL libraries. May be repeated. |
| `--source` | FHIR source path. |
| `--source-type` | `filesystem`, `directory`, `ndjson`, or `json`. |
| `--source-format` | Filesystem source format. |
| `--valuesets` | ValueSet file or directory. May be repeated. |
| `--period` | Measurement period as `START:END`. |
| `--audit-mode` | `none`, `population`, or `full`. |
| `--narratives` | Generate audit narratives. |
| `--patient-id` | Restrict to a patient id. May be repeated. |
| `--filter-to-ip` | Only emit Initial Population rows. |
| `--format` | Result format: `json`, `csv`, or `parquet`. May be repeated. |
| `--measure-reports` | `none`, `summary`, `individual`, or `both`. |
| `--definitions` | `none` or `all`. |
| `--definition-format` | Definition format. May be repeated. |
| `--include-sde-definitions` | Include `SDE*` definitions in `--definitions all`. |
| `--fail-fast` | Stop after the first measure failure. |

## Output Files

For each successful measure, the batch runner can write:

| File | Description |
|------|-------------|
| `results.<format>` | Patient-level population results. |
| `summary.json` | Aggregate counts, rate, and stratifiers. |
| `MeasureReport-summary.json` | FHIR summary MeasureReport when enabled. |
| `individual-reports/<patient>.json` | FHIR individual MeasureReport resources when enabled. |
| `definitions.<format>` | Machine-readable CQL define outputs when enabled. |
| `definitions.schema.json` | Mapping from output columns to CQL define names. |

The root output directory also contains `run.json` with batch-level status,
duration, per-measure outputs, and errors.

## MeasureReport Extensions

Summary reports include the DEQM performance rate extension:

```text
http://hl7.org/fhir/us/davinci-deqm/StructureDefinition/performanceRate
```

Individual reports include:

- DEQM individual MeasureReport profile:
  `http://hl7.org/fhir/us/davinci-deqm/StructureDefinition/indv-measurereport-deqm`
- `subject.reference` set to `Patient/<id>`.
- `MeasureReport.text` narrative generated from population membership.
- Authored Measure group/population ids when available.
- R5 backport linkId extensions for authored group/population ids.
- `cqf-supportingEvidence` extensions for Measure-authored supporting evidence.

Supporting evidence values are serialized as FHIR value types when possible:
booleans, integers, decimals, strings, references, codings, CodeableConcepts,
Quantities, Periods, tuples, empty lists, and absent values. Audit trace metadata
is not serialized into `cqf-supportingEvidence`; if audit output wraps a value as
`{result, evidence}`, the extension receives only `result`.

## Compliance

The DQM conformance suite currently passes the QI-Core 2025 measure corpus:

| Suite | Status |
|-------|--------|
| CMS eCQM QI-Core 2025 | 47/47 measures |
| Unified spec conformance | 2822/2822 tests |
