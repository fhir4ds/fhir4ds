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
- `fhir_model.py` — `_fhir_model_lock` added for singleton init (2026-Q2 refresh)
- `strings.py` — `_MAX_REGEX_LENGTH` guard added against ReDoS
- `strings.py` — `_REDOS_PATTERNS` detector added for nested quantifiers (2026-Q2 refresh)
- `cql/duckdb/udf/string.py` — same ReDoS guards applied to deprecated CQL UDFs

### CQL Translator Invariants
The 8 architecture invariants documented in `docs/architecture/translator/AGENTS.md`
remain in effect. Post-remediation status (2026-Q2):
- `SQLRaw` mid-pipeline: **20+ sites eliminated** (CQL-001/002/012-016/018-020/025)
- `to_sql()` mid-pipeline: **8 sites fixed** (replaced with proper AST nodes)
- Silent fallbacks: **Fixed** (context.py warns, cte_builder uses registry)
- Strategy 2 templates: **1 active system** (`fluent_functions.py` `body_sql`) — blocked, requires Task C4
- Hardcoded resource types: **Fully externalized** — fallback set in `queries.py` removed, now uses only `schema.resources.keys()`
- Magic strings: `"Measurement Period"`, `"Patient"`, `"Initial Population"` extracted to module constants (`CQL_MEASUREMENT_PERIOD`, `CQL_PATIENT_CONTEXT`, `_DEFAULT_FINAL_DEFINITION`)

### ViewDefinition Canonical Constants
Built-in FHIRPath variables (`%context`, `%resource`, `%rootResource`, `%ucum`, `%rowIndex`)
are canonically defined in `fhir4ds/viewdef/constants.py:FHIRPATH_BUILTIN_VARIABLES`.
The generator imports from this canonical source. Do not duplicate this set.

See `docs/architecture/CQL_TRANSLATOR_AUDIT_2026Q2.md` for the detailed issue log.

### C++ Extension Security
All JSON injection sites have been remediated with `escapeJsonString()`.
- `evaluator.cpp:711` type() — **fixed** (uses escapeJsonString)
- `interval.cpp` to_json() string bounds — **fixed** (Pass 4)
- `interval.cpp` width_string() — already safe (numeric output only)
- `quantity.cpp` wrapInConcept — **null deref fixed** (Pass 4)
**3 ReDoS risks** exist in `matches()`/`replaceMatches()` —
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

---

## WASM / Pyodide Release Checklist

This section documents the recurring release steps required to keep the WASM demo working. Missing any of these steps causes Pyodide initialization failures in the CQL playground.

### Why This Breaks Every Release

`fhir4ds-v2` lists `duckdb~=X.Y.Z` as a Python dependency in `pyproject.toml`. In the browser, DuckDB is provided by **DuckDB-WASM** (JavaScript). There is no pure Python wheel for `duckdb` on PyPI — micropip cannot install it. This causes micropip to fail before the fhir4ds wheel is installed.

Additionally, `fhir4ds/cql/__init__.py` has a top-level `import duckdb` that must succeed at import time in Pyodide, even though DuckDB connections are never used in the translation code path.

Both issues are permanently mitigated:
1. **`fhir4ds/cql/__init__.py`**: `import duckdb` is wrapped in `try/except ImportError` that installs a minimal stub. The CQL translator works without the real duckdb package.
2. **`web/wasm-demo/src/workers/pyodide.worker.ts`**: Uses `micropip.install(wheel, deps=False)` and manually installs only the pure-Python deps (`antlr4-python3-runtime`, `python-dateutil`).

### Release Steps for WASM Demo

Every release must complete **all** of the following steps:

1. **Build the wheel:**
   ```bash
   cd /path/to/fhir4ds
   hatch build -t wheel
   # Output: dist/fhir4ds_v2-X.Y.Z-py3-none-any.whl
   ```

2. **Copy the wheel to `public/`:**
   ```bash
   cp dist/fhir4ds_v2-X.Y.Z-py3-none-any.whl web/wasm-demo/public/
   ```
   The `vite.config.ts` auto-discovers the newest `fhir4ds_v2-*.whl` in `public/` at build time. Remove the old wheel to avoid confusion.

3. **Remove the old wheel:**
   ```bash
   # Keep only the current version
   ls web/wasm-demo/public/fhir4ds_v2-*.whl
   rm web/wasm-demo/public/fhir4ds_v2-OLD_VERSION-py3-none-any.whl
   ```

4. **Update version references in docs and wasm-engine.md:**
   Search `web/website/docs/` and `web/wasm-demo/` for `fhir4ds_v2-OLD_VERSION` and update to the new version.

5. **Update `__version__` in subpackages:**
   All four subpackages must be updated to the new version:
   - `fhir4ds/cql/__init__.py`
   - `fhir4ds/dqm/__init__.py`
   - `fhir4ds/fhirpath/__init__.py`
   - `fhir4ds/viewdef/__init__.py`
   
   The root `fhir4ds/__init__.py` version is set by `pyproject.toml` via hatch; subpackage `__version__` strings must be updated manually.

6. **Build the WASM demo:**
   ```bash
   cd web/wasm-demo && npm run build
   ```

7. **⚠️ Deploy the build to the website static directory:**
   ```bash
   # Remove old build and replace with the fresh one
   rm -rf web/website/static/wasm-app
   cp -r web/wasm-demo/dist/. web/website/static/wasm-app/
   ```
   **This step is critical.** The website (`web/website/`) serves the WASM demo from
   `static/wasm-app/` — a pre-built snapshot that is NOT automatically updated when
   `web/wasm-demo/` is rebuilt. Skipping this step causes the website's CQL playground
   to silently use the stale build (old worker without `deps=False`, old wheel name, etc.)
   while the standalone demo works correctly, making the bug hard to diagnose.

8. **Run Playwright tests to verify (standalone + web component):**
   ```bash
   cd web/wasm-demo && npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts
   # All 11 tests must pass
   ```

### Pyodide Dependency Constraints

The Pyodide worker (`web/wasm-demo/src/workers/pyodide.worker.ts`) installs deps with `deps=False` and manually lists the required pure-Python deps:
- `antlr4-python3-runtime>=4.10` — CQL grammar parser
- `python-dateutil>=2.8` — date/time arithmetic in CQL

If new pure-Python dependencies are added to `fhir4ds-v2` that are required for CQL translation (not just data loading), they must be added to this manual install list in the worker.

**Do NOT add duckdb to this list.** DuckDB is provided by DuckDB-WASM and the Python stub in `fhir4ds/cql/__init__.py` handles the import-time reference.
