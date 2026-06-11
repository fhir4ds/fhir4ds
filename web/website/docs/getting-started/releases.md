---
id: releases
title: What's New
---

# What's New

This page summarizes the major changes in each release of FHIR4DS.

## Version 0.0.9
*June 2026*

Version 0.0.9 is a release-preparation hardening cycle focused on preserving
the full conformance baseline while revalidating infrastructure domains,
release metadata, public documentation, browser assets, and benchmark evidence.

### Highlights

- **Release Readiness Campaign**: Revalidates FHIRPath, CQL, SQL-on-FHIR
  ViewDefinition, ingestion/source adapters, DQM audit evidence, installation,
  and environment behavior across the scheduled 0.0.9 evolution loop.
- **Version and Artifact Alignment**: Package metadata, public subpackage
  versions, notebook snippets, website install references, and WASM translator
  wheel references are aligned with `0.0.9`.
- **Validation Gates**: The release-prep pipeline includes conformance,
  package pytest, documentation audit, benchmark validation, and final scribe
  handoff gates before completion.

### Upgrade

```bash
pip install fhir4ds-v2==0.0.9
```

---

## Version 0.0.8
*June 2026*

Version 0.0.8 focuses on Mongo-backed FHIR server integration, FHIR `$cql`
conformance-runner compatibility, release hardening, public API robustness,
audit evidence fidelity, and refreshed browser/package artifacts while
preserving the full conformance baseline.

### Highlights

- **Mongo FHIR Server Integration**: Added `MongoFhirServerSource` for
  read-only analytics over Mongo-backed FHIR servers through DuckDB's community
  `mongo_scan` extension, with support for per-resource, explicit, and shared
  collection layouts.
- **Mongo DQM Materialization**: Added `fhir4ds dqm mongo ...` commands and
  worker support for durable patient-change queues, change-stream processing,
  result/audit storage, optional generated `MeasureReport` publishing, and
  patient-scoped source pushdown.
- **FHIR `$cql` Facade**: Added a narrow local FHIR R4 `$cql` operation facade
  and `fhir4ds cql-server` CLI for running `cqframework/cql-tests-runner`
  against the FHIR4DS CQL engine.
- **CQL Spec Parity Sweep**: Tightened CQL primitive, clinical, temporal,
  interval, list, quantity/ratio, conversion, rounding, and no-Python/native
  DuckDB parity behavior across the conformance surface.
- **FHIRPath Native Parity**: Native DuckDB FHIRPath now rejects malformed
  Section 5.1 existence-helper arities, including specialized `exists()` and
  FHIR-specific `hasValue()` dispatch paths, in parity with the Python
  fallback.
- **Measurement Period Fidelity**: CQL-authored `Interval<DateTime>` parameter
  defaults retain DateTime precision and authored open/closed boundary flags
  through DQM population SQL generation.
- **Public API Error Contracts**: DQM config loaders, HAPI/Mongo
  materialization config parsing, and filesystem sources now raise actionable
  package errors for malformed public inputs.
- **Audit Evidence Accuracy**: Multi-group DQM audit pruning preserves
  group-local causal resource targets, and Mongo compact materialization now
  mirrors the HAPI compact result/full audit split.
- **Release Artifact Consistency**: Package metadata, public subpackage
  versions, notebook snippets, CQL runner metadata, wheel contents, and WASM
  translator assets are aligned with `0.0.8`.

### Bug Fixes

- **CQL `$cql` Runner Compatibility**: FHIR `Parameters` serialization now
  handles intervals, empty/null values, temporal values, quantities, ratios,
  Codes, Concepts, Lists, and Tuples in runner-compatible shapes, and runner
  report status now reflects JSON-level failures even when the Node process
  exits successfully.
- **CQL Semantic Edge Cases**: Fixed ratio literals, Long metadata
  preservation, DateTime null precision, decimal equivalence, interval
  null/open-bound behavior, interval uncertainty propagation, `ToString`
  formatting, and public `Round`/`RoundTo` half-away-from-zero behavior across
  Python fallback, native-loaded DuckDB, and no-Python/browser-style surfaces.
- **Measurement Period Fidelity**: CQL-authored `Interval<DateTime>` parameter
  defaults retain DateTime precision and authored open/closed boundary flags
  through DQM population SQL generation.
- **Public API Error Contracts**: DQM config loaders, HAPI/Mongo
  materialization config parsing, and filesystem sources now raise actionable
  package errors for malformed public inputs instead of leaking decoder or
  attribute errors.
- **Audit Evidence Accuracy**: Multi-group DQM audit pruning preserves
  group-local causal resource targets, and Mongo compact materialization now
  mirrors the HAPI compact result/full audit split.
- **Release Artifact Consistency**: Package metadata, public subpackage
  versions, notebook snippets, CQL runner metadata, wheel contents, website
  release surfaces, and browser demo assets are aligned with `0.0.8`.

### Conformance

| Suite | Passed | Total | Rate |
|-------|-------:|------:|-----:|
| ViewDefinition v2 | 134 | 134 | 100.0% |
| FHIRPath R4 | 935 | 935 | 100.0% |
| CQL | 1,706 | 1,706 | 100.0% |
| DQM QI-Core 2025 | 47 | 47 | 100.0% |
| Overall | 2,822 | 2,822 | 100.0% |

### Upgrade

```bash
pip install fhir4ds-v2==0.0.8
```

---

## Version 0.0.7
*May 2026*

Version 0.0.7 focuses on release readiness, SQL safety, audit evidence accuracy, and packaging consistency. It preserves the 100% conformance posture while tightening loader boundaries, DQM population attribution evidence, and native/Python fallback release gates.

### Highlights

- **Compiled Measures API**: Introduced `compile_measure()` and `execute_compiled_measure()` in the DQM API. This allows parsing and compiling CQL to SQL once, enabling highly efficient batched execution across patient cohorts.
- **Artifact Resolvers**: Replaced static file-path dependencies with a pluggable `ArtifactResolver` interface (`FileArtifactResolver` and `HapiArtifactResolver`), enabling dynamic resolution of Measures, CQL libraries, and ValueSets from file systems or remote FHIR servers.
- **HAPI FHIR Integration**: Added `HapiPostgresSource` for querying HAPI FHIR JPA Server PostgreSQL backends in place, along with comprehensive guides for event-driven DQM materialization.

### Bug Fixes

- **FHIRPath Native Parity**: Massively tightened the behavior of the C++ DuckDB extension to exactly match the Python fallback across arithmetic overflows, collection equality, singleton evaluation, string reflection, and edge-case Boolean precedence.
- **CQL Type Inference**: Fixed row shapes and nested tuples generated during compiled measure materialization so `Query` and `Return` clauses preserve complex type structure correctly across batch runs.
- **CQL Optimization**: Ensure degenerate intervals (e.g. `[x, x]`) safely propagate through `StartsSame` and `EndsSame` temporal operators without triggering DuckDB null-handling faults.
- **CQL Temporal Intervals**: Optimized interval overlap SQL handles null low bounds using CQL interval semantics instead of propagating SQL NULL.
- **DQM Audit Evidence**: Exclusion-style audit narratives use effective population masks so denominator exceptions and numerator exclusions match final population attribution rules.
- **Loader SQL Safety**: Custom resource and ValueSet table names are quoted consistently, including SQL keywords such as `select` and `where`.
- **FHIR JSON Validation**: File, URL, directory, and DQM ValueSet loaders now reject non-object JSON cleanly instead of leaking implementation errors.

### Conformance

| Suite | Passed | Total | Rate |
|-------|-------:|------:|-----:|
| ViewDefinition v2 | 134 | 134 | 100.0% |
| FHIRPath R4 | 935 | 935 | 100.0% |
| CQL | 1,706 | 1,706 | 100.0% |
| DQM QI-Core 2025 | 47 | 47 | 100.0% |
| Overall | 2,822 | 2,822 | 100.0% |

### Upgrade

```bash
pip install fhir4ds-v2==0.0.7
```

---

## Version 0.0.6
*May 2026*

Version 0.0.6 focuses on release hardening, browser runtime parity, and clinical correctness for HEDIS/DQM workflows. The release preserves 100% conformance across ViewDefinition, FHIRPath, CQL, and DQM while tightening the packaged DuckDB extension boundary.

### Highlights

- **C++ DuckDB WASM Parity**: Browser-required CQL interval, boundary, date/quantity, interval set, logical, list, valueset, and FHIRPath repeat functions are available through C++ extensions.
- **No-Python Runtime Gate**: Added direct-extension tests that load packaged C++ extensions without registering Python fallback UDFs.
- **100% Conformance Gate**: ViewDefinition (134/134), FHIRPath R4 (935/935), CQL (1,706/1,706), and DQM QI-Core 2025 (47/47) all pass.
- **HEDIS Clinical Logic**: Calendar age helpers, episode aggregate folds, repeated-extension predicates, interval boundaries, stratifiers, and reference resolution were hardened for native DuckDB, Python fallback, and browser-style execution.
- **DQM Reporting**: Measure group stratifiers are parsed, evaluated, summarized, and exported in MeasureReport output.
- **Packaging Safety**: The wheel pins DuckDB to `1.5.2` so installed Python dependencies match the bundled native extension ABI.
- **WASM Assets**: Updated translator wheel to `fhir4ds_v2-0.0.6-py3-none-any.whl` and rebuilt DuckDB extension side modules.

### Bug Fixes

- **CQL**: Patient-context `AgeIn*At(asOf)` now routes through `CalculateAgeIn*At(birthDate, asOf)` helpers for leap-day and calendar-period parity.
- **CQL**: Query aggregate list folds preserve typed empty-list semantics so HEDIS episode deduplication counts episode collections correctly.
- **CQL**: `resolve()` accepts `ResourceType/id`, bare ids, full URLs ending in `ResourceType/id`, and JSON Reference objects.
- **DQM**: Proportion summaries now assign patient/case population labels before aggregation so exclusions and exceptions are counted in the correct order.
- **Sources**: Strict NDJSON loading is all-or-nothing for both malformed JSON and valid-JSON invalid-FHIR records.
- **CSV Source**: Constructor inputs are validated at the public API boundary before SQL projection registration.

### Upgrade

```bash
pip install fhir4ds-v2==0.0.6
```

---

## Version 0.0.5
*May 2026*

Version 0.0.5 continues the **100% Compliance Milestone** — every conformance suite passes at 100%, totaling 2,822 tests across CQL, FHIRPath, ViewDefinition, and DQM.

### Highlights

- **100% Spec Compliance**: All test suites now pass at 100% — CQL (1,706/1,706), FHIRPath (935/935), ViewDefinition (134/134), and DQM (47/47 measures).
- **CQL Gap Closure**: Resolved remaining 2 CQL spec tests — `RolledOutIntervals` (DuckDB correlated UNNEST workaround) and `IntegerIntervalProperlyIncludedInNullBoundaries` (spec ambiguity resolved).
- **DQM Full Pass Rate**: All 47 QI-Core 2025 CMS eCQMs now pass. 4 measures have documented upstream test data accuracy gaps (CMS135, CMS145, CMS157, CMS1017) that affect all conformant engines equally.
- **ReactiveEvaluator API Update**: `ReactiveEvaluator` constructor now accepts `measure_bundle` and `cql_library_path` parameters, aligning with the `MeasureEvaluator` API.
- **Interval JSON Handling**: Fixed precision comparisons to correctly handle interval JSON in CQL temporal operations.

### Bug Fixes

- **CQL**: Fixed interval JSON parsing in precision comparisons (affected CMS157 and related temporal tests).
- **CQL**: Prevented parser loop and enforced inline recursion limit for deeply nested expressions.
- **CQL**: Fixed `RolledOutIntervals` — implemented alternative approach avoiding DuckDB correlated UNNEST limitation.
- **DQM**: Fixed CMS157 test data — corrected measurement period alignment with encounter dates.

### API Changes

- **`ReactiveEvaluator.__init__`**: Parameters changed from `(con, measure, adapter)` to `(con, measure_bundle, cql_library_path, adapter)`.
- **Version Bump**: All `fhir4ds` packages bumped to version `0.0.5`.
- **WASM Assets**: Updated translator wheel for the 0.0.5 release series.

### Upgrade

```bash
pip install fhir4ds-v2==0.0.5
```

---

## Version 0.0.3
*April 2026*

Version 0.0.3 introduces the **Zero-ETL Source Adapter** architecture, enabling CQL measures, FHIRPath queries, and ViewDefinitions to run directly against external data without copying it into DuckDB.

### Highlights

- **Zero-ETL Source Adapters**: Run clinical logic directly against Parquet data lakes, PostgreSQL databases, and CSV files — no data movement, no PHI duplication.
- **New API**: `fhir4ds.attach()`, `fhir4ds.detach()`, and `create_connection(source=...)` provide a uniform lifecycle for all data sources.
- **Schema Validation at Registration**: `SchemaValidationError` is raised immediately at `attach()` time if the adapter's view doesn't conform — fail fast, not during measure evaluation.
- **Backward Compatibility**: `ExistingTableSource` provides the adapter interface over pre-loaded data. No breaking changes for `FHIRDataLoader` users.

### New: Source Adapters

| Adapter | Purpose |
|---------|---------|
| `FileSystemSource` | Parquet, NDJSON, Iceberg files — local or cloud (S3, Azure, GCS) |
| `PostgresSource` | FHIR JSON stored in PostgreSQL columns |
| `ExistingTableSource` | Wraps pre-loaded DuckDB tables in the adapter API |
| `CSVSource` | Flat CSV files with user-defined SQL projection |

#### FileSystemSource
- Supports Parquet (default), NDJSON, JSON, and Iceberg formats.
- Cloud storage via `CloudCredentials` (S3, Azure, GCS).
- Hive partition pruning for large datasets.
- Incremental delta tracking via file mtime.

#### PostgresSource
- Attaches to Postgres via DuckDB's `postgres` extension (read-only).
- `PostgresTableMapping` defines column-to-schema mappings per table.
- All identifiers quoted via `quote_identifier()` — prevents SQL injection from user-supplied names.
- **Scope boundary**: Requires FHIR JSON in a column. Relational-to-FHIR column mapping is out of scope.

#### ExistingTableSource
- Wraps any existing DuckDB table/view in the adapter API.
- Validates schema at registration time.
- Zero migration cost for current `FHIRDataLoader` users.

#### CSVSource
- User provides a `projection_sql` with a `{source}` placeholder.
- Full control over how flat CSV columns map to FHIR JSON (via `json_object()`).

### New API

- **`fhir4ds.attach(con, adapter)`** — Registers a source adapter on an existing connection.
- **`fhir4ds.detach(con, adapter)`** — Unregisters an adapter, dropping the view and cleaning up.
- **`fhir4ds.create_connection(source=adapter)`** — Mounts a source immediately on connection creation.
- **`SourceAdapter` Protocol** — Interface contract for third-party adapter implementations (`register()`, `unregister()`).
- **`SchemaValidationError`** — Raised at registration time if the adapter schema doesn't conform.
- **`validate_schema()`** — Validates the `resources` view against the required schema contract.
- **`quote_identifier()`** — Safely quotes identifiers to prevent SQL injection.
- **`CloudCredentials`** — Encapsulates DuckDB secret configuration for S3, Azure, and GCS.

### Security

- **Identifier Quoting**: `PostgresSource` and `ExistingTableSource` use `quote_identifier()` to prevent SQL injection from user-supplied table and column names.
- **Scope Boundary**: `PostgresSource` documentation clearly states it requires FHIR JSON in a column — preventing misuse as a generic relational mapper.

### Known Limitations

- `PostgresSource` requires FHIR JSON in a Postgres column — constructing FHIR JSON from arbitrary relational schemas is not supported in this release.
- `CSVSource` does not support incremental delta tracking.
- `FileSystemSource` incremental tracking is mtime-based and may produce false positives.
- Iceberg format does not support incremental delta tracking.

### Migration Guide

Existing `FHIRDataLoader` users have **no breaking changes**. To adopt the adapter pattern:

```python
# Before (still works, no changes needed):
loader = FHIRDataLoader(con)
loader.load_directory('/data/fhir/')

# After (optional — adds uniform adapter API):
from fhir4ds.sources import ExistingTableSource
source = ExistingTableSource()
fhir4ds.attach(con, source)
```

### Upgrade

```bash
pip install fhir4ds-v2==0.0.3
```

### API Changes

- **Version Bump**: All `fhir4ds` packages bumped to version `0.0.3`.
- **WASM Assets**: Updated translator wheel to `fhir4ds_v2-0.0.3-py3-none-any.whl`.
- **New Module**: `fhir4ds.sources` — exported from the top-level `fhir4ds` namespace.

---

## Version 0.0.2
*April 2026*

Version 0.0.2 focuses on reaching full spec compliance, enhancing performance through architectural optimizations and a new C++ extension, and hardening security.

### Highlights

- **Near-Full Spec Conformance**: Achieved 99.8% conformance across CQL, DQM, FHIRPath, and ViewDefinition test suites, resolving over 150 identified gaps.
- **69.5x Performance Boost**: Evaluation speed has increased significantly due to a hybrid C++/Python execution model and optimized metadata caching.
- **DuckDB v1.5.2 Integration**: Fully stabilized on the latest DuckDB version, including optimized WASM builds for browser-side execution.
- **Standardized Conformance Logging**: A new unified logging framework provides detailed pass/fail reporting across all engine components.

### Performance Improvements

- **Registry Caching**: `MeasureEvaluator` now caches FHIR schemas and profile registries, eliminating redundant 1.5MB allocations per evaluation call.
- **Audit Deduplication**: Optimized "Full" audit mode to automatically deduplicate Cartesian product results generated by complex LEFT JOINs in retrieve CTEs.
- **C++ Extension Parity**: Reached 100% feature parity between the Python UDFs and the high-performance C++ extension, allowing for hybrid execution that combines C++ speed with Python's flexibility.

### Security Fixes

- **JSON Injection Remediation**: Fixed critical JSON injection vulnerabilities in the C++ evaluator's `type()` and `width_string()` functions.
- **Thread Safety**: Added synchronization locks to singleton registries and cache stores (`profile_registry`, `fhir_loader`, `variable_store`) to prevent race conditions in multi-threaded environments.
- **ReDoS Protection**: Implemented guards on maximum regex lengths to prevent Regular Expression Denial of Service attacks in string manipulation logic.

### Enhancements

#### CQL Translator
- **Point-to-Interval Promotion**: Added automatic promotion of point operands to degenerate intervals (e.g., `[x, x]`) for `StartsSame` and `EndsSame` operators to ensure spec-compliant temporal comparisons.
- **Distinct List Aggregates**: Added support for standard aggregates (`Sum`, `Min`, `Max`, `Avg`) on distinct list literals.
- **Clinical UDF Macros**: Externalized clinical logic into structured DuckDB macros for better maintainability.

#### FHIRPath Engine
- **Cross-Namespace Equivalence**: Updated `TypeInfo` to correctly treat FHIR primitive types and their System equivalents as the same type per FHIRPath §5.1.
- **Conversion Function Flexibility**: Support for both functional and member invocation forms for `convertsToX` functions (e.g., `convertsToBoolean(v)` and `v.convertsToBoolean()`).
- **Semantic Temporal Validation**: Added strict validation for calendar dates and times, including month day limits and leap year checks.

#### DQM & ViewDefinition
- **Enhanced Narratives**: Improved narrative generation for population results when detailed evidence capture is disabled.
- **ViewDef String Escaping**: Updated the SQL generator to correctly handle backslashes and single quotes within FHIRPath strings in ViewDefinitions.

#### Infrastructure & Tooling
- **Centralized Logging**: Added a new unified logging framework that tracks pass rates and failure details across all subprojects.
- **Build-Time Auto-Discovery**: Improved the build system to auto-discover DuckDB versions and wheel names, ensuring smoother Pyodide package installations.
- **Benchmarking Submodule**: Added `tests/data/dqm-content-qicore-2026` as a git submodule to provide a standard set of 2026 QI Core measures for benchmarking.

### Bug Fixes

- **CQL**: Fixed circular definition handling (QA-019) which previously caused `RecursionError` in complex libraries.
- **CQL**: Fixed `Count(distinct(defRef))` producing invalid SQL when referencing non-existent columns.
- **FHIRPath**: Resolved a regression in `DateTime > Date` comparisons.
- **FHIRPath**: Fixed type compatibility logic in equality operators to correctly return `empty` for incompatible types per §6.1.1.
- **ViewDefinition**: Fixed a regression in time boundary generation where an unnecessary 'T' prefix was occasionally added.

### API Changes

- **Version Bump**: The `fhir4ds`, `fhir4ds.cql`, `fhir4ds.fhirpath`, and `fhir4ds.viewdef` packages have all been bumped to version `0.0.2`.
- **WASM Assets**: Updated the required WASM assets; integrations must now use the `0.0.2` translator wheel.

---

## Version 0.0.1
*Initial Release - Early 2026*

The initial release established the foundation for the FHIR4DS engine.

- **Unified Interface**: Provided a single entry point for CQL, FHIRPath, and ViewDefinition execution.
- **DuckDB Integration**: Implemented the first set of Python-based UDFs for FHIR logic.
- **Initial WASM Support**: Demonstrated browser-side clinical reasoning using Pyodide and DuckDB-WASM.
