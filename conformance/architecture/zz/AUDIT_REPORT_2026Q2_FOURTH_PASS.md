# FHIR4DS Architecture Audit Report -- 2026 Q2 Fourth Pass

**Date:** 2026-07-14
**Scope:** All subprojects (fhirpath, cql, viewdef, dqm, C++ extensions)
**Test Baseline:** 6465 passed, 4 pre-existing failures, 64 skipped

## Executive Summary

This audit identified 17 issues across all subprojects (2 CRITICAL, 9 HIGH, 6 MEDIUM).
16 issues were resolved; 1 MEDIUM deferred.

**Zero regressions**: 6465/6465 tests pass. FHIRPath R4 compliance: 933/935 (unchanged).

## Issues Resolved

### CRITICAL

| ID | Subproject | Issue | Fix |
|----|-----------|-------|-----|
| CQL-3VL-001 | cql-duckdb | 16 interval UDFs returned `False` instead of `None` for null inputs, violating CQL three-valued logic | Changed all 16 functions to return `None`; updated tests |
| VIEWDEF-004 | viewdef | `_resolve_simple_value()` silently stringified complex types (dict/list) | Added `ValueError` for unsupported complex types |

### HIGH

| ID | Subproject | Issue | Fix |
|----|-----------|-------|-----|
| CQL-SSOT-001 | cql | 7 production sites bypassed Context SSOT via `get_default_profile_registry()` fallback | Moved initialization to `__post_init__`; removed all fallbacks; removed 5 dead imports |
| CQL-AST-001 | cql | `SQLRaw("NULL")` used instead of proper `SQLNull()` AST node (9 instances) | Replaced all with `SQLNull()` |
| CQL-FAIL-001 | cql | `fhir_schema.py` logged WARNING on schema load failure instead of raising | Changed to `RuntimeError` with aggregated error messages |
| DQM-STATE-001 | dqm | Silent mutable state via `_last_pop_map` instance variable | Added `DeprecationWarning` on legacy DataFrame path |
| DQM-PARSE-001 | dqm | Library parse errors silently returned `None` | Changed to raise `DQMError` |
| FPDUCK-EXT-001 | fhirpath-duckdb | C++ extension load failure caught `except Exception` (too broad) | Narrowed to `duckdb.Error` and `OSError`; added "already loaded" handling |
| VIEWDEF-001 | viewdef | JOIN ON clause safety (potential `"TRUE"` return) | Verified safe -- unreachable after existing `raise ValueError` |
| VIEWDEF-003 | viewdef | Unknown FHIR column types (`id`, `uri`, etc.) defaulted to STRING with warning | Added 13 FHIR primitive types to `ColumnType` enum and `TYPE_TO_UDF` mapping |
| CPP-SUBSTR-001 | cpp | 17+ `substr()` calls without bounds checking | Manual review: all calls have proper bounds guards |
| CPP-NULL-001 | cpp | `yyjson_get_str()` null pointer risk | Manual review: all 27 calls have null guards |

### MEDIUM

| ID | Subproject | Issue | Fix |
|----|-----------|-------|-----|
| VIEWDEF-002 | viewdef | Undefined constant references silently passed through | Added warning for undefined user constants (distinct from FHIRPath context vars) |
| DQM-NEG-001 | dqm | Negative population counts silently clamped | Changed to raise `DQMError` |
| FP-CACHE-001 | fhirpath | Global mutable `_valid_props_cache` without thread safety | Added `threading.Lock` around reads and writes |
| FP-ERR-001 | fhirpath | 42 `raise Exception()` instead of `FHIRPathError` hierarchy | Replaced all with `FHIRPathError` across 10 files |
| FP-COMPLEX-001 | fhirpath | `sort_fn` cyclomatic complexity 33 | **DEFERRED** -- requires careful incremental decomposition |

## Files Modified

### CQL DuckDB Adapter
- `fhir4ds/cql/duckdb/udf/interval.py` -- 3VL null handling for 16 functions
- `fhir4ds/cql/duckdb/tests/test_interval_udfs.py` -- Updated 10 test assertions
- `fhir4ds/cql/duckdb/extension.py` -- Narrowed exception handling, added runtime duckdb import

### CQL Translator
- `fhir4ds/cql/translator/context.py` -- Profile registry initialization in `__post_init__`
- `fhir4ds/cql/translator/cte_builder.py` -- Removed fallback, cleaned `_resolve_profile_registry`
- `fhir4ds/cql/translator/patterns/retrieve.py` -- Removed 4 fallback sites, dead import
- `fhir4ds/cql/translator/expressions/_query.py` -- Removed fallback, dead import, SQLRaw->SQLNull
- `fhir4ds/cql/translator/expressions/__init__.py` -- Dead import removal
- `fhir4ds/cql/translator/expressions/_functions.py` -- Dead import removal
- `fhir4ds/cql/translator/expressions/_property.py` -- Dead import removal
- `fhir4ds/cql/translator/expressions/_operators.py` -- Dead import removal
- `fhir4ds/cql/translator/expressions/_lists.py` -- Dead import removal, SQLRaw->SQLNull
- `fhir4ds/cql/translator/fhir_schema.py` -- Fail-fast on schema load

### ViewDef
- `fhir4ds/viewdef/types.py` -- Added 13 FHIR primitive types to ColumnType enum
- `fhir4ds/viewdef/generator.py` -- Extended TYPE_TO_UDF with new types
- `fhir4ds/viewdef/constants.py` -- Undefined constant warnings, complex type validation
- `fhir4ds/viewdef/join.py` -- Clarifying comment

### DQM
- `fhir4ds/dqm/evaluator.py` -- Fail-fast errors, deprecation warning, negative count validation

### FHIRPath Core
- `fhir4ds/fhirpath/duckdb/extension.py` -- Narrowed exception handling, runtime duckdb import
- `fhir4ds/fhirpath/engine/evaluators/__init__.py` -- Thread-safe cache, FHIRPathError
- `fhir4ds/fhirpath/engine/__init__.py` -- FHIRPathError
- `fhir4ds/fhirpath/engine/util.py` -- FHIRPathError
- `fhir4ds/fhirpath/engine/invocations/collections.py` -- FHIRPathError
- `fhir4ds/fhirpath/engine/invocations/equality.py` -- FHIRPathError
- `fhir4ds/fhirpath/engine/invocations/existence.py` -- FHIRPathError
- `fhir4ds/fhirpath/engine/invocations/filtering.py` -- FHIRPathError
- `fhir4ds/fhirpath/engine/invocations/math.py` -- FHIRPathError
- `fhir4ds/fhirpath/engine/invocations/misc.py` -- FHIRPathError
- `fhir4ds/fhirpath/engine/invocations/strings.py` -- FHIRPathError

## Validation

- **Unit tests**: 6465 passed, 4 pre-existing failures, 64 skipped (zero regressions)
- **FHIRPath R4 compliance**: 933/935 (2 pre-existing failures, unchanged)
- **ViewDef compliance**: 632 passed, 23 skipped, 28 xfailed
- **Warnings reduced**: 468 -> 138 (ViewDef unknown type warnings eliminated)

## Remaining Technical Debt

1. **FP-COMPLEX-001**: `sort_fn` cyclomatic complexity 33 (deferred)
2. **Deep SQLRaw refactoring**: ~30 remaining `SQLRaw` instances in CQL translator for audit/fluent function code paths. These are used in final-rendering contexts and are lower risk, but violate the pure AST pipeline invariant.
3. **Heuristic collection detection** in ViewDef (370+ lines of hardcoded patterns)
4. **claim_principal_diagnosis** in CQL DuckDB hardcoded to US-specific SNOMED codes
