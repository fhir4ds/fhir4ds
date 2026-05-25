---
id: dqm
title: fhir4ds.dqm
sidebar_label: dqm
---

# `fhir4ds.dqm`

The `fhir4ds.dqm` module provides orchestration for Digital Quality Measures (DQM). It handles parsing FHIR `Measure` resources, compiling their referenced CQL libraries, executing the logic against a DuckDB `resources` view, and generating standards-compliant outputs (like FHIR `MeasureReport` resources).

The module supports both direct programmatic evaluation via `MeasureEvaluator` and configured bulk processing via the Batch Runner.

```python
from fhir4ds.dqm import MeasureEvaluator, AuditMode, create_artifact_resolver
from fhir4ds.dqm.batch import run_batch
from fhir4ds.dqm.config import load_run_config
```

---

## 1. Core Evaluation API

The core API is built around `MeasureEvaluator`, which executes clinical logic on a DuckDB connection.

### `MeasureEvaluator`

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

#### `evaluate(...)`

Evaluates a FHIR `Measure` directly. Best for single-patient tests, notebooks, and dynamic execution.

```python
result = evaluator.evaluate(
    measure_ref="./measures/Measure-CMS124.json",
    cql_library_path="./cql/CMS124FHIR.cql",
    parameters={"Measurement Period": ("2025-01-01", "2025-12-31")},
    audit_mode=AuditMode.POPULATION,
    patient_ids=["patient-123"],
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `measure_ref` | `str | Path | dict` | Path to Measure JSON, canonical URL, or an already parsed Measure dict. |
| `cql_library_path` | `str | Path | None` | Optional path to the main CQL file (if not resolved dynamically). |
| `artifact_resolver` | `ArtifactResolver | None` | Custom resolver for loading Measures and ValueSets (see Artifact Resolvers below). |
| `parameters` | `dict | None` | CQL parameter overrides. Use `{"Measurement Period": (start, end)}` for MeasureReport period inference. |
| `audit_mode` | `str | AuditMode` | `none`, `population`, or `full`. |
| `filter_to_ip` | `bool` | Return only rows meeting Initial Population. |
| `patient_ids` | `list[str] | None` | Restrict evaluation to selected patient ids. |
| `include_paths` | `list[str] | None` | Directories used to resolve included CQL libraries. |

Returns a `MeasureResult`.

#### `compile_measure(...)` and `execute_compiled_measure(...)`

For production workloads, `compile_measure` parses the Measure and CQL to generate optimized, reusable DuckDB SQL. You can then execute this compiled plan repeatedly across batches of patients.

```python
compiled = evaluator.compile_measure(
    measure_ref="http://example.org/fhir/Measure/CMS122|2025",
    artifact_resolver=resolver,
    patient_scope="target_table",
)

first = evaluator.execute_compiled_measure(compiled, patient_ids=["p1", "p2"])
second = evaluator.execute_compiled_measure(compiled, patient_ids=["p3"])
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `patient_scope` | `str` | `"literal"` embeds `patient_ids` in generated SQL. `"target_table"` leaves patient IDs for execution time. |
| `patient_ids` (compile) | `list[str] | None` | Allowed only with `patient_scope="literal"`. Included in the cache key. |
| `patient_ids` (execute) | `list[str]` | Required with `patient_scope="target_table"`. |

DuckDB prepared statements are scoped to the connection and created lazily on first execution. 

#### Output Generators

Once a `MeasureResult` is obtained, it can be formatted:

- `evaluator.summary_report(result)`: Returns aggregate counts, performance rate, and stratifiers.
- `evaluator.to_csv(result, path)`: Writes the result DataFrame to a CSV.
- `evaluator.to_measure_report(result, report_type="summary", ...)`: Creates a FHIR `MeasureReport` dict (`summary` or `individual`).

### `MeasureResult`

The raw output of an evaluation.

```python
@dataclass
class MeasureResult:
    dataframe: pandas.DataFrame
    populations: dict[str, Any]
    parameters: dict[str, Any]
    measure_url: str | None = None
    pop_map: PopulationMap | None = None
```

---

## 2. Artifact Resolvers

Rather than passing hardcoded file paths, the engine uses an `ArtifactResolver` to fetch `Measure`, `Library` (CQL), and `ValueSet` resources.

### `create_artifact_resolver(...)`

A factory function to instantiate built-in resolvers. If an `artifact_resolver` is passed to `evaluate` or `compile_measure`, legacy path arguments (like `cql_library_path` and `include_paths`) are ignored in favor of the resolver's strategy.

#### File Resolver

```python
from fhir4ds.dqm import create_artifact_resolver

# File-based resolution
file_resolver = create_artifact_resolver(
    "files",
    include_paths=["./cql/includes"],
    valueset_paths=["./terminology/valuesets"],
)
```

`valueset_paths` may point to ValueSet JSON files, directories containing JSON files, or Bundles containing ValueSet resources. A CQL `valueset` declaration can use either `canonical` or `canonical|version`; versioned declarations are matched to the corresponding ValueSet `version`. File-backed ValueSets must contain either an `expansion` element or direct `compose.include.concept` entries.

#### HAPI Resolver

```python
# HAPI FHIR resolution
hapi_resolver = create_artifact_resolver(
    "hapi",
    hapi_base_url="http://localhost:18080/fhir",
    hapi_headers={"Authorization": "Bearer token"},
    hapi_unversioned_valueset_policy="latest",
)
```

The HAPI resolver accepts Measure ids, `Measure/<id>` references, and canonical URLs. ValueSets declared in the primary CQL library and transitive includes are resolved from HAPI by canonical URL and optional version.

If a HAPI ValueSet does not already contain loadable terminology, the resolver calls `$expand` using the canonical URL and version. Unversioned references that match multiple ValueSet resources try candidate versions newest-first. Set `hapi_unversioned_valueset_policy="error"` to reject ambiguous unversioned references and require a CQL `version` qualifier.

### `ArtifactResolver` Protocol

The stable extension point for custom implementers is `ArtifactResolver`:

- `resolve_measure(ref)`
- `resolve_library(ref=None, *, measure=None, measure_source_id=None)`
- `resolve_include(alias, version=None)`
- `resolve_valueset(ref)`
- `resolve_valuesets_for_cql(cql_text)`
- `fingerprint()`

---

## 3. Audit Configurations

### `AuditMode`

Controls the depth of evidence collected during evaluation.

| Value | Description |
|-------|-------------|
| `AuditMode.NONE` / `"none"` | No audit wrapping. Fastest mode, returns bare booleans. |
| `AuditMode.POPULATION` / `"population"` | Captures retrieve/resource-level evidence for population outputs. Best for most production debugging. |
| `AuditMode.FULL` / `"full"` | Wraps all expressions with audit macros for deep expression-level traceability. Heaviest cost. |

### `AuditOrStrategy`

| Value | Description |
|-------|-------------|
| `AuditOrStrategy.TRUE_BRANCH` | (Default) Keep evidence only from the branch that made the CQL `or` expression true. |
| `AuditOrStrategy.ALL` | Keep evidence from all `or` branches. |

---

## 4. Batch Runner & Configuration

For pipeline processing, `fhir4ds` provides a declarative batch runner configured via JSON or YAML.

### `run_batch(config)`

Executes all configured measures and writes the outputs directly to the specified directory.

```python
from fhir4ds.dqm.batch import run_batch
from fhir4ds.dqm.config import load_run_config

config = load_run_config("dqm-run.json")
batch_result = run_batch(config)
```

Other batch utilities:
- `validate_config(config)`: Returns a list of validation errors.
- `inspect_config(config)`: Returns a JSON-serializable diagnostic description of the planned run.

### `DQMRunConfig`

The root configuration dataclass loaded from the JSON/YAML file.

```python
DQMRunConfig(
    measures: list[MeasureSpec],
    source: SourceSpec,
    outputs: OutputSpec,
    terminology: TerminologySpec = TerminologySpec(),
    parameters: dict = {},
    period_start: str | None = None,
    period_end: str | None = None,
    audit: AuditSpec = AuditSpec(),
)
```

#### Example Configuration (`dqm-run.json`)

```json
{
  "measures": [
    {
      "id": "CMS124",
      "path": "./measures/Measure-CMS124.json",
      "cql": "./cql/CMS124FHIR.cql"
    }
  ],
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
    "mode": "population"
  },
  "outputs": {
    "directory": "./dqm-output",
    "formats": ["json", "parquet"],
    "measure_reports": "both"
  }
}
```

---

## 5. Standard Outputs

When executing via `run_batch`, the engine generates the following files in the specified output directory for each Measure:

| File | Description |
|------|-------------|
| `results.<format>` | Patient-level population results (e.g. `initial_population: true`). |
| `summary.json` | Aggregate counts, overall rate, and stratifiers. |
| `MeasureReport-summary.json` | FHIR summary MeasureReport (when `measure_reports` is enabled). |
| `individual-reports/<patient>.json` | FHIR individual MeasureReport resources. |
| `definitions.<format>` | Machine-readable outputs for specific CQL `define` statements. |

### MeasureReport Extensions

Generated MeasureReports automatically include several official extensions:

- **DEQM Performance Rate**: Added to summary reports.
- **DEQM Individual Profile**: Added to individual reports alongside `subject.reference`.
- **`cqf-supportingEvidence`**: Populated with Measure-authored supporting evidence (serialized into native FHIR types).
- **R5 Backport `linkId`**: Added for authored group/population ids to aid traceability.
