---
id: releases
title: What's New
---

# What's New

This page summarizes the major changes in each release of FHIR4DS.

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
