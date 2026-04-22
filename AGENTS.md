# duckdb-fhirpath - AGENTS.md

**FHIR for Data Science** - A unified suite of high-performance tools for working with FHIR data in analytical environments, built on DuckDB.

## Repository Overview

This repository has been reorganized into a unified `fhir4ds` namespace. All Python source code resides under the `fhir4ds/` directory, organized by feature and backend.

## Package Structure (Unified)

| Feature | Subpackage Path | Purpose |
|---------|-----------------|---------|
| **FHIRPath** | `fhir4ds.fhirpath` | Core FHIRPath parser and evaluator |
| **FHIRPath (DuckDB)** | `fhir4ds.fhirpath.duckdb` | DuckDB integration and C++ extension wrapper |
| **CQL** | `fhir4ds.cql` | CQL to SQL translator for clinical quality measures |
| **CQL (DuckDB)** | `fhir4ds.cql.duckdb` | CQL-specific DuckDB UDFs and macros |
| **ViewDefinition** | `fhir4ds.viewdef` | SQL-on-FHIR v2 ViewDefinition support |
| **DQM** | `fhir4ds.dqm` | Digital Quality Measure orchestrator |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                          │
│  CQL Measures  │  FHIRPath Queries  │  ViewDefinitions         │
└────────┬───────────────┬───────────────────┬───────────────────┘
         │               │                   │
         ▼               ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      TRANSLATION LAYER                          │
│  fhir4ds.cql  │  (direct)          │  fhir4ds.viewdef          │
│  CQL → SQL    │                    │  ViewDef → SQL            │
└────────┬───────────────┴───────────────────┴───────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      UDF LAYER (DuckDB)                         │
│  fhir4ds.fhirpath.duckdb     │  fhir4ds.cql.duckdb             │
│  fhirpath(), fhirpath_text() │  AgeInYears(), DurationInDays() │
└────────┬───────────────────────┴────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE LAYER                                 │
│  fhir4ds.fhirpath                                               │
│  FHIRPath parser and evaluator engine                           │
└─────────────────────────────────────────────────────────────────┘
```

## Subpackage Details

### `fhir4ds.fhirpath`
**Purpose:** Core FHIRPath parser and evaluator.
**Location:** `fhir4ds/fhirpath/`
**Tests:** `fhir4ds/fhirpath/tests/unit/`

### `fhir4ds.fhirpath.duckdb`
**Purpose:** Native DuckDB integration.
**Location:** `fhir4ds/fhirpath/duckdb/`
**Bundled Extension:** `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`

### `fhir4ds.cql`
**Purpose:** CQL translator and measure evaluator.
**Location:** `fhir4ds/cql/`
**Compliance:** 100% of implemented features pass official CQL compliance.

### `fhir4ds.viewdef`
**Purpose:** SQL-on-FHIR v2 implementation.
**Location:** `fhir4ds/viewdef/`
**Compliance:** 100% compliance with ViewDefinition v2 specification.

---

## Official Compliance Testing

The project maintains a unified conformance suite for validating against official standards.

```bash
# Run all conformance tests (FHIRPath, CQL, ViewDef, DQM)
python3 conformance/scripts/run_all.py
```

Reports are generated in `conformance/reports/`.

---

## Development Workflow
...
- **Benchmarks:** `benchmarks/`
- **Official Tests:** `tests/data/` (Heavy datasets and submodules)

1. Implementation: `fhir4ds/fhirpath/engine/invocations/`
2. Tests: `fhir4ds/fhirpath/tests/unit/`
3. DuckDB Registration: `fhir4ds/fhirpath/duckdb/udf.py`

### Adding a New CQL Function
1. Translation: `fhir4ds/cql/translator/functions.py`
2. UDF Implementation: `fhir4ds/cql/duckdb/udf/`
3. Registration: `fhir4ds/cql/duckdb/extension.py`

---

## Known Architecture Issues (2026-Q2 Refresh Audit)

See `docs/architecture/AUDIT_REPORT_2026Q2_REFRESH.md` for the full audit report.

### Error Hierarchy
FHIRPath error classes are canonically defined in `fhir4ds/fhirpath/engine/errors.py`.
The DuckDB adapter layer re-exports them from `fhir4ds/fhirpath/duckdb/errors.py`.
**Do not** define new error classes in the DuckDB layer that duplicate core classes.

### Thread Safety
Thread-safety mitigations applied in 2026-Q2 remediation:
- `constants.py` — `Constants()` is per-invocation (already safe; no action needed)
- `TypeInfo.model` — deprecated; never set in production code (documented, planned removal)
- `variable.py` — `_VARIABLE_STORES_LOCK` added for double-checked locking
- `profile_registry.py` — `_default_registry_lock` added for singleton init
- `fhir_loader.py` — `_CACHE_LOCK` added for `WeakKeyDictionary` access
- `strings.py` — `_MAX_REGEX_LENGTH` guard added against ReDoS

### CQL Translator Invariants
The 8 architecture invariants documented in `docs/architecture/translator/AGENTS.md`
remain in effect. Post-remediation status (2026-Q2):
- `SQLRaw` mid-pipeline: **20+ sites eliminated** (CQL-001/002/012-016/018-020/025)
- `to_sql()` mid-pipeline: **8 sites fixed** (replaced with proper AST nodes)
- Silent fallbacks: **Fixed** (context.py warns, cte_builder uses registry)
- Strategy 2 templates: **1 active system** (`fluent_functions.py` `body_sql`) — blocked, requires Task C4
- Hardcoded resource types: **Externalized** (query `schema.resources.keys()`, module constants)

See `docs/architecture/CQL_TRANSLATOR_AUDIT_2026Q2.md` for the detailed issue log.

### C++ Extension Security
17 of 19 JSON injection sites have been remediated with `escapeJsonString()`.
**2 HIGH-severity sites remain** (`evaluator.cpp:711` type(), `interval.cpp:578`
width_string()). **3 ReDoS risks** exist in `matches()`/`replaceMatches()` —
`std::regex` backtracking engine is vulnerable to catastrophic backtracking.
RE2 migration or complexity limits required before production with untrusted input.

## Asset Relocation Reference

- **C++ Source:** `extensions/fhirpath/` and `extensions/cql/`
- **Web Demos:** `web/wasm-demo/` and `web/website/`
- **Benchmarks:** `benchmarks/`
- **Conformance Runner:** `fhir4ds/dqm/tests/conformance/`
- **Test Data:** `tests/data/` (submodules: ecqm-content-qicore-2025, dqm-content-qicore-2026)
- **Conformance Output:** `tests/output/` (gitignored, regenerated by conformance runner)
- **Benchmark Output:** `benchmarks/output/` (gitignored, regenerated by run_comparison.py)
