# Comprehensive Architecture Audit Report

**Version**: 3.0
**Date**: 2026-04-08
**Scope**: All 8 subprojects in duckdb-fhirpath monorepo
**Status**: Follow-up Audit (v2.0 remediations verified; new findings identified)
**Prior Version**: v2.0 (2026-04-04)

---

## Executive Summary

This is a follow-up audit verifying v2.0 remediations and performing deeper analysis. The codebase is functionally mature with strong compliance: 97.65% FHIRPath R4 (913/935), 100% CQL parsing (2981/2981), 100% SQL-on-FHIR v2 (140/140). Prior P1-P3 remediations are confirmed solid. This audit identifies 13 actionable issues that the prior audit either missed, incompletely fixed, or deprioritized.

### Test Baselines (2026-04-08)

| Package | Passed | Skipped | XFailed | XPassed | Notes |
|---------|--------|---------|---------|---------|-------|
| fhirpath-py | 132 | 0 | 0 | 0 | 97.65% FHIRPath R4 compliance |
| duckdb-fhirpath-py | 940 | 0 | 0 | 0 | 1 pytest warning (test returning bool) |
| sql-on-fhir-py | 632 | 23 | 28 | 0 | 100% SQL-on-FHIR v2 compliance |
| duckdb-cql-py | 405 | 5 | 0 | 0 | |
| cql-py | 4291 | 97 | 1 | 2 | 100% CQL parsing compliance |
| dqm-py | 60 | 6 | 0 | 0 | |

### Findings Summary (New in v3.0)

| Category | Critical | High | Medium | Total |
|----------|----------|------|--------|-------|
| Dead/Deprecated Code | 1 | 0 | 0 | 1 |
| Silent Fallbacks | 0 | 1 | 3 | 4 |
| Hardcoded Domain Knowledge | 0 | 1 | 0 | 1 |
| Anti-Patterns | 0 | 3 | 3 | 6 |
| Design Flaws | 0 | 0 | 1 | 1 |
| **Total** | **1** | **5** | **7** | **13** |

---

## 1. fhirpath-py

### 1.1 Hardcoded FHIR Type Data (HIGH)

**Background**: Three large dictionaries in `nodes.py` (lines 1248-1460+) hardcode FHIR R4 type information: `VALID_FHIR_TYPES` (25 entries), `FHIR_PATH_TO_TYPE` (150 lines, 5 resource types only), and `FHIR_TYPE_HIERARCHY`. All have TODO comments acknowledging the need to externalize.

**Design Strategy**: Extract to JSON files under `models/r4/` directory. Load via a `FHIRModelLoader` class that accepts a version parameter.

**Acceptance Criteria**:
- AC1: `VALID_FHIR_TYPES`, `FHIR_PATH_TO_TYPE`, and `FHIR_TYPE_HIERARCHY` are loaded from JSON files, not defined in Python source.
- AC2: All 132 unit tests pass unchanged.
- AC3: A `models/r4/` directory contains `valid_types.json`, `path_to_type.json`, `type_hierarchy.json`.

### 1.2 Silent Exception Handlers (MEDIUM)

**Background**: `evaluators/__init__.py` lines 233-234 and 295-296 have bare `except: pass` blocks that mask AttributeError and TypeError during choice type resolution and type conversion. `util.py:40-42` catches generic `Exception` during Quantity conversion.

**Design Strategy**: Replace with specific exception types. Log at DEBUG level. In the `except AttributeError` case for immutable dicts, this is acceptable but should have a debug log.

**Acceptance Criteria**:
- AC1: No bare `except: pass` remains in the codebase.
- AC2: All silent handlers either log at DEBUG level or raise.
- AC3: 132 unit tests pass. 97.5% FHIRPath compliance unchanged.

### 1.3 FP_TimeBase.plus() Complexity (MEDIUM)

**Background**: 149-line method at `nodes.py:600-748` with 4-5 nesting levels, 19 precision/unit/time-type combinations, and magic numbers (24, 30, 60, 365). Logic is duplicated across DateTime, Date, and Time variants.

**Design Strategy**: Extract a `_UNIT_CONVERSION` lookup table mapping (time_unit, precision) to conversion functions. Replace nested if-chains with table-driven dispatch.

**Acceptance Criteria**:
- AC1: Method reduced to <60 lines using table-driven dispatch.
- AC2: All compliance tests pass. No behavioral changes.
- AC3: Magic numbers replaced with named constants.

### 1.4 Incomplete conformsTo() (LOW)

**Background**: `misc.py:278-344` hardcodes only 5 FHIR resource types in `fhir_type_hierarchy`. Returns `[False]` for unmapped types.

**Design Strategy**: Load type hierarchy from the same externalized JSON as issue 1.1.

---

## 2. duckdb-fhirpath-py

### 2.1 Silent Error Swallowing in UDFs (CRITICAL)

**Background**: `udf.py:199-213` and `extension.py:93-134` catch ALL exceptions (JSONDecodeError, FHIRPathSyntaxError, FHIRPathError, generic Exception) and return empty lists `[]`. Users cannot distinguish "field absent" from "syntax error in expression" without setting `FHIRPATH_STRICT_MODE=1`.

**Design Strategy**: Introduce a three-tier error model:
1. `STRICT` mode (env var): raise all errors.
2. `WARN` mode (default): log at WARNING level with expression and error details for syntax/parse errors; return `[]` only for data-access errors.
3. `SILENT` mode: current behavior.

**Acceptance Criteria**:
- AC1: FHIRPathSyntaxError always logged at WARNING level, never silently swallowed.
- AC2: `FHIRPATH_ERROR_MODE` env var controls behavior (strict/warn/silent).
- AC3: 939 tests pass. No behavioral regression in warn mode.

### 2.2 Dead Vectorized UDF Code (REVISED: NOT DEAD)

**Background**: Initial audit flagged `udf.py:117-218` as dead. Further investigation revealed it IS called by `fhirpath_udf_typed()`. However, the "vectorized" function immediately converts Arrow arrays to Python lists, defeating the purpose of vectorization.

**Design Strategy**: Document the misleading naming. Consider renaming to `_batch_evaluate` to clarify that it processes batches row-by-row, not in a truly vectorized manner.

### 2.3 Per-Row Python Execution (MEDIUM, Performance)

**Background**: Each row triggers: JSON parse -> FHIRPath compile -> evaluate -> JSON serialize. LRU cache for JSON parsing (64 entries) has poor hit rate since FHIR resources have unique IDs.

**Design Strategy**: Increase expression cache (already at 1024) but accept per-row cost as architectural trade-off. Document that the C++ extension should be used for performance-critical workloads. Remove misleading "vectorized" label.

### 2.4 Stray Test File (LOW)

**Background**: `test_quantity_udf.py` exists at package root, outside `tests/` directory. Not discovered by pytest.

**Design Strategy**: Move to `tests/unit/test_quantity_udf.py`.

---

## 3. sql-on-fhir-py

### 3.1 Duplicate Type Definitions (HIGH)

**Background**: `parser.py:13-168` and `types.py:61-358` define near-identical dataclasses (Column, Select, Constant, Join, ViewDefinition). `types.py` has enum validation; `parser.py` does not. `generator.py:41-46` has a TYPE_CHECKING hack importing from different modules.

**Design Strategy**: Consolidate all type definitions in `types.py` as the canonical source. Update `parser.py` to import from `types.py`. Remove the TYPE_CHECKING conditional in `generator.py`.

**Acceptance Criteria**:
- AC1: `parser.py` imports Column, Select, Constant, Join, ViewDefinition from `types.py`.
- AC2: No duplicate dataclass definitions exist.
- AC3: `generator.py` imports unconditionally from `types.py`.
- AC4: 631 tests pass unchanged.

### 3.2 Dead Code in union.py (MEDIUM)

**Background**: `union.py:138-167` defines `_generate_lateral_join_if_needed()` which calls `generator.generate_element_var()` -- a method that does not exist. This function is never called; UNION handling is fully implemented in `generator.py:601-663`.

**Design Strategy**: Remove the dead function. Verify no references exist.

**Acceptance Criteria**:
- AC1: `_generate_lateral_join_if_needed` removed from `union.py`.
- AC2: All tests pass.

### 3.3 Missing Logging (LOW)

**Background**: Only `generator.py` has a logger. `parser.py`, `constants.py`, `join.py`, `unnest.py`, `union.py` have no logging. Users have no visibility into decision-making.

**Design Strategy**: Add `_logger = logging.getLogger(__name__)` to all modules. Log at DEBUG level for resolution decisions, WARNING for fallbacks.

---

## 4. cql-py

### 4.1 Deprecated Generator Package (MEDIUM)

**Background**: `src/cql_py/generator/` contains the deprecated string-based SQL generator. `population_builder.py:343-349` has a data-corruption bug: `.replace("true", "TRUE")` corrupts string literals containing "true". All files have DEPRECATED docstrings and `DeprecationWarning`.

**Design Strategy**: The V2 translator is the primary path. The deprecated generator should be removed entirely or moved to an `_archived/` directory. Since it has deprecation warnings, removal is safe.

**Acceptance Criteria**:
- AC1: `src/cql_py/generator/` removed from the package.
- AC2: No imports of `cql_py.generator` remain in production code.
- AC3: All 4296 tests pass (tests referencing the generator may be updated or removed).

### 4.2 "Measurement Period" Special-Casing (MEDIUM)

**Background**: `context.py:390,480,1012` special-case "Measurement Period" with dedicated fields and pre-registration logic. Three TODO comments acknowledge this.

**Design Strategy**: Treat "Measurement Period" as a regular interval parameter through `parameter_bindings`. Remove `_measurement_period` field and `set_measurement_period()` method. Route through generic parameter handling.

**Acceptance Criteria**:
- AC1: No `_measurement_period` field in `SQLTranslationContext`.
- AC2: "Measurement Period" accessed via `parameter_bindings["Measurement Period"]`.
- AC3: All 4296 tests pass. 42/46 benchmark measures unaffected.

### 4.3 Hardcoded Fluent Function Stubs (MEDIUM)

**Background**: `fluent_functions.py:281-295` hardcodes QICoreCommon/Status library function definitions. These should be loaded from configuration.

**Design Strategy**: Create `resources/terminology/fluent_function_stubs.json` containing the function definitions. Load at translator initialization via `ModelConfig`.

**Acceptance Criteria**:
- AC1: No hardcoded function names in `fluent_functions.py`.
- AC2: Function definitions loaded from JSON config.
- AC3: All tests and benchmarks pass.

### 4.4 QICore Prefix Stripping (LOW)

**Background**: `profile_registry.py:149-152` hardcodes `QICore-` and `QICore` prefix stripping as fallback for profile resolution.

**Design Strategy**: Move to `ProfileRegistry` configuration loaded from `qicore-profiles.json`.

---

## 5. duckdb-cql-py

### 5.1 Bare Exception Handlers (HIGH)

**Background**: 48+ bare `except Exception` handlers across all UDF files (`age.py`, `datetime.py`, `clinical.py`, `quantity.py`, `interval.py`, `valueset.py`). All log a warning and return `None`, masking bugs in FHIR data parsing.

**Design Strategy**: Replace generic `except Exception` with specific types:
- `orjson.JSONDecodeError` for JSON parsing
- `ValueError` for date/number parsing
- `KeyError` for missing fields
Log at appropriate levels. Keep `None` returns for expected missing-data scenarios.

**Acceptance Criteria**:
- AC1: No bare `except Exception` remains. All handlers catch specific exception types.
- AC2: Each handler has a log message identifying the exception type.
- AC3: 405 tests pass unchanged.

### 5.2 Hardcoded QICore Extension URLs (MEDIUM)

**Background**: `valueset.py:200-205` hardcodes `_QICORE_EXTENSION_PROPS` mapping three QICore extension property names to URLs.

**Design Strategy**: Load from a JSON configuration file. Accept the mapping as a parameter to the registration function.

### 5.3 Single-Quote JSON Hack (MEDIUM)

**Background**: `interval.py:56-62` catches `JSONDecodeError`, then retries with `.replace("'", '"')`. This masks upstream bugs where `fhirpath_text` returns Python repr instead of JSON.

**Design Strategy**: Fix the upstream serialization in `duckdb-fhirpath-py` to always produce valid JSON. Remove the hack once upstream is fixed.

### 5.4 in_valueset Placeholder (INFORMATIONAL)

**Background**: `extension.py:65-71` registers a placeholder `in_valueset` that always raises. This is intentional -- the real implementation requires loaded valueset data. Documented behavior.

---

## 6. dqm-py

### 6.1 Temporal Coupling in Evaluator (MEDIUM)

**Background**: `evaluator.py:40-41` stores `_last_pop_map` and `_last_parameters` as mutable instance state. `to_measure_report()` (line 248-253) depends on these being set by `evaluate()`. Calling `to_measure_report()` before `evaluate()` raises a cryptic error.

**Design Strategy**: Make `to_measure_report()` accept explicit parameters:
```python
def to_measure_report(self, pop_map: PopulationMap, parameters: dict) -> dict:
```
Remove mutable state fields.

**Acceptance Criteria**:
- AC1: `to_measure_report()` accepts pop_map and parameters as explicit args.
- AC2: `_last_pop_map` and `_last_parameters` removed.
- AC3: Backward compatibility via optional args with deprecation warning.
- AC4: 66 tests pass.

### 6.2 Dead Code and Unused Parameters (LOW)

**Background**: `max_evidence_items` parameter (evaluator.py:30,37) stored but never read. `population_basis` parsed (parser.py:78-89) but never used. `_extract_evidence_from_row` (evaluator.py:384-415) never called.

**Design Strategy**: Remove all dead code. If features are planned, track in issues not dead code.

---

## 7. duckdb-fhirpath-cpp

### 7.1 Monolithic evaluator.cpp (LOW, Design Debt)

**Background**: 4,911 lines in a single file. Difficult to navigate and maintain.

**Design Strategy**: Split into `binary_ops.cpp`, `functions.cpp`, `navigation.cpp`, `serialization.cpp`.

### 7.2 Hardcoded FHIR Field Type Map (MEDIUM)

**Background**: `evaluator.cpp:140-175` has only 40 hardcoded field→type mappings. Unknown fields default to "unknown".

**Design Strategy**: Generate from FHIR R4 StructureDefinitions at build time. Create a code generation script.

### 7.3 Incomplete DateTime Precision (MEDIUM)

**Background**: `cql_extension.cpp:670-727` `SameOrBefore/After` functions handle only year, month, day precision. Hour, minute, second, millisecond silently fall back to full millisecond comparison.

**Design Strategy**: Add missing precision levels following CQL specification.

---

## 8. duckdb-cql-cpp

### 8.1 Duplicate UCUM Tables (LOW)

**Background**: Unit conversion tables defined separately in `fhirpath/evaluator.cpp:90-115` and `cql/quantity.cpp:23-100`. Divergence risk.

**Design Strategy**: Extract to shared `src/include/ucum_units.hpp` header.

### 8.2 Already-Fixed Issues (Informational)

The following were identified but confirmed fixed per AGENTS.md remediation:
- Thread-local parser (race condition fix)
- `catch(...)` replaced with `catch(const std::exception&)`
- Negative age clamping returns NULL
- Statistical mode uses full double precision
- Mutex-protected valueset cache
- Magic numbers extracted to named constants

---

## Remediation Execution Order

### Priority 1 -- Immediate (safety, correctness)
1. **dead-code-removal**: Remove deprecated generator in cql-py, dead vectorized UDF in duckdb-fhirpath-py, dead code in sql-on-fhir-py union.py, dead code in dqm-py.
2. **silent-fallback-audit**: Fix bare exception handlers across duckdb-cql-py and duckdb-fhirpath-py.

### Priority 2 -- Short-term (architecture)
3. **sof-type-consolidation**: Consolidate sql-on-fhir-py type definitions.
4. **fhirpath-externalize-types**: Move hardcoded FHIR types to JSON.
5. **dqm-temporal-coupling**: Fix evaluator API coupling.
6. **dqm-dead-params**: Remove dead parameters.

### Priority 3 -- Medium-term (quality, performance)
7. **cql-measurement-period**: Generalize Measurement Period.
8. **cql-fluent-stubs**: Config-drive fluent function stubs.
9. **fhirpath-refactor-plus**: Simplify datetime arithmetic.
10. **cpp-ucum-consolidation**: Merge UCUM tables.

### Priority 4 -- Long-term (design debt)
11. **cpp-split-monoliths**: Split large C++ files.

---

## Cross-Cutting Themes

### Theme 1: Silent Fallbacks

The most pervasive anti-pattern. Found in every Python subproject. The codebase favors returning empty/None/False over raising errors, making it extremely difficult to debug incorrect results. The FHIRPath spec does mandate empty-collection semantics for missing data, but syntax errors and JSON parse failures should never be silently swallowed.

### Theme 2: Hardcoded Domain Knowledge

FHIR type mappings, QICore extension URLs, profile name prefixes, and resource type hierarchies are hardcoded in Python source and C++ source. This creates a maintenance burden when FHIR versions change and prevents the libraries from being used with non-standard profiles.

### Theme 3: Deprecated Code Still Present

The cql-py `generator/` package has been deprecated but remains, including a data-corruption bug in string replacement. Dead code in sql-on-fhir-py, duckdb-fhirpath-py, and dqm-py increases maintenance burden and confuses contributors.

### Theme 4: Inconsistent Error Models

Each package handles errors differently. fhirpath-py raises exceptions. duckdb-fhirpath-py swallows them. duckdb-cql-py logs warnings. dqm-py returns None. A unified error handling strategy across the stack would improve debuggability.

---

## Remediation Status (Updated 2026-04-04)

### Completed (v2.0 - 2026-04-04)

| Item | Package | Change | Tests |
|------|---------|--------|-------|
| dead-code-removal | sql-on-fhir-py | Removed broken `_generate_lateral_join_if_needed` from union.py | 632 passed |
| dead-code-removal | dqm-py | Removed unused `max_evidence_items` parameter | 66 passed |
| dead-code-removal | duckdb-fhirpath-py | Moved stray test_quantity_udf.py to tests/unit/ | 940 passed |
| silent-fallback-audit | duckdb-cql-py | Narrowed 20 bare `except Exception` to specific types across age.py, datetime.py, clinical.py, ratio.py, valueset.py | 405 passed |
| sof-type-consolidation | sql-on-fhir-py | Removed duplicate dataclasses from parser.py; consolidated on types.py as canonical source; updated generator.py and join.py for enum handling | 632 passed |
| fhirpath-externalize-types | fhirpath-py | Moved VALID_FHIR_TYPES, FHIR_PATH_TO_TYPE, FHIR_TYPE_HIERARCHY to JSON files in models/r4/ | 132 passed |
| fhirpath-refactor-plus | fhirpath-py | Refactored 149-line `plus()` into 3 focused methods with table-driven unit conversion; eliminated magic numbers | 132 + 940 passed |
| cql-measurement-period | cql-py | Cleaned stale TODOs; field already synced with `_parameter_bindings` via `set_measurement_period()` | 4296 passed |
| cql-fluent-stubs | cql-py | Moved 7 hardcoded `FunctionDefinition` stubs to `resources/terminology/fluent_function_stubs.json`; loaded dynamically | 4296 passed |
| cpp-ucum-consolidation | C++ extensions | Created shared `ucum_units.hpp` header with canonical unit table; evaluator.cpp and quantity.cpp both delegate to it | N/A (C++ build env unavailable) |
| dqm-temporal-coupling | dqm-py | Already mitigated by MeasureResult pattern | 66 passed |

### Completed (v3.0 - 2026-04-08)

| Item | Package | Change | Tests |
|------|---------|--------|-------|
| CQL-GEN-CORRUPT | cql-py | Removed deprecated `generator/` package with data-corruption bug (.replace("true","TRUE")). Archived to `archived/cql-py-generator/`. Removed 74 deprecated tests. | 4217 passed |
| FP-COPY-PASTE-CMP | fhirpath-py | Extracted 4 identical comparison functions (lt/gt/lte/gte) into shared `_compare()` helper with lambda dispatch | 132 + 940 passed |
| FP-DUP-BOUNDARY | fhirpath-py | Extracted lowBoundary/highBoundary shared logic into `_boundary()`, `_time_boundary()`, `_date_boundary()`, `_datetime_boundary()` helpers with fill-value config dicts | 132 + 940 passed |
| FP-MAGIC-NUMS | fhirpath-py | Extracted magic numbers to named constants: `FHIRPATH_MAX_PRECISION=28`, `DEFAULT_OUTPUT_PRECISION=8`, `CONTEXT_PRECISION_MIN=40` | 132 passed |
| DFP-EXCEPT-BLANKET | duckdb-fhirpath-py | Replaced 17 bare `except Exception` handlers with specific types across udf.py, extension.py, evaluator.py, filter.py, existence.py, typecheck.py. Removed all `# noqa: BLE001` suppressions. | 940 passed |
| DFP-THREAD-IMPORT | duckdb-fhirpath-py | Replaced `__import__('threading').Lock()` with proper `import threading` at module level | 940 passed |
| DCQ-QICORE-HARDCODED | duckdb-cql-py | Moved `_QICORE_EXTENSION_PROPS` from inside function body to module-level `QICORE_EXTENSION_PROPS` constant with documentation | 405 passed |
| DCQ-JSON-HACK | duckdb-cql-py | Replaced unsafe `.replace("'", '"')` JSON hack with `ast.literal_eval()` for safe Python literal parsing | 405 passed |
| DCQ-EXCEPT-BARE | duckdb-cql-py | Narrowed 3 remaining `except Exception` to specific types in age.py and valueset.py | 405 passed |
| DCQ-DEEP-NEST | duckdb-cql-py | Refactored dateAddQuantity: extracted `_TIMEDELTA_UNITS` lookup table, `_YEAR_UNITS`/`_MONTH_UNITS` frozensets, moved imports to module level | 405 passed |
| DQM-EXCEPT-BARE | dqm-py | Narrowed bare `except Exception` in library loader to `(SyntaxError, ValueError, KeyError)` | 60 passed |
| SOF-LOGGING | sql-on-fhir-py | Added `_logger = logging.getLogger(__name__)` to parser.py, constants.py, union.py, join.py, unnest.py | 632 passed |

### Benchmark Validation (v3.0)

- **2025 suite (post-remediation)**: 46/46 successful, 42/46 perfect, 4 known upstream (matches v2.0 baseline)
- **FHIRPath R4 compliance**: 913/935 (97.65%) — matches baseline

### Remaining (P4 - Long-term)

| Item | Package | Notes |
|------|---------|-------|
| cpp-split-monoliths | C++ extensions | evaluator.cpp (4889 lines) and cql_extension.cpp (2339 lines) should be split into logical modules. Requires C++ build environment. |
| CPP-CQL-PRECISION | duckdb-cql-cpp | SameOrBefore/After only handles year-second precision; silently defaults to Millisecond for unknown. Requires C++ build environment. |
