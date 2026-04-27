# Engineer Handoff — Iteration 8 FIX Phase

## Summary

Iteration 8 addressed 5 QA issues. 2 FIXED, 1 INTENDED, 2 DEFERRED.

## Issues

### QA8-002 (HIGH): FIXED — Circular include detection
**Problem:** Mutual CQL library includes (`A→B→A`) caused unbounded recursion / stack overflow.

**Fix:** Added `_resolving_stack` (frozenset of `(path, version)` tuples) to `CQLToSQLTranslator`. Before recursing into an included library, the current library identity is pushed onto the stack. Child translator instances receive the parent stack plus the new entry. `CircularIncludeError` (new subclass of `TranslationError` in `fhir4ds/cql/errors.py`) is raised with the full include chain when a cycle is detected. Diamond dependencies (A→B, A→C, B→D, C→D) are unaffected — the existing cache handles deduplication.

**Files changed:**
- `fhir4ds/cql/errors.py` — Added `CircularIncludeError`
- `fhir4ds/cql/translator/translator.py` — Added `_resolving_stack` parameter and field
- `fhir4ds/cql/translator/include_handler.py` — Cycle detection before recursive load
- `fhir4ds/cql/tests/unit/test_include_errors.py` — 4 tests (direct, transitive, diamond-safe, chain metadata)

### QA8-001 (MEDIUM): FIXED — Broken SQL from unresolvable includes
**Problem:** When no `library_loader` is configured and CQL references an included library's definitions, the translator silently generated SQL referencing undefined CTEs.

**Fix:** Unresolved includes are tracked in `context._unresolved_includes`. Expression translation in `_property.py` and `_core.py` checks this set when encountering a qualified reference to an included library (e.g., `SomeLib."Def1"`). If the include is unresolved, a clear `TranslationError` is raised at translate time instead of at SQL execution time. Includes are still registered in context for introspection (e.g., test_cms124 cross-library reference tests).

**Side fix:** Swapped `_process_parameters` before `_process_includes` in `translate_library()` to match the order in `translate_library_to_population_sql()`. This ensures parameters are registered even if include resolution fails.

**Files changed:**
- `fhir4ds/cql/translator/context.py` — `_unresolved_includes` set, `mark_include_unresolved()`, `is_include_unresolved()`
- `fhir4ds/cql/translator/expressions/_property.py` — Unresolved include check
- `fhir4ds/cql/translator/expressions/_core.py` — Unresolved include check
- `fhir4ds/cql/translator/translator.py` — Parameter processing order fix
- `fhir4ds/cql/tests/integration/test_smoke_ci_gate.py` — Skip measures needing unresolved includes
- `fhir4ds/cql/tests/unit/test_include_errors.py` — 3 tests (reference raises, registered-without-reference, no-includes-ok)

### QA8-003 (MEDIUM): INTENDED — ViewDef resourceType filter
**Assessment:** The filter is only added when `source_table` is explicitly configured. The SQL-on-FHIR v2 spec defines ViewDefinition as operating on a shared `resources` table, so the filter is correct per spec. Per-resource tables are non-standard and users opting into `source_table` are using the shared-table model.

### QA8-004 (LOW): DEFERRED — in_valueset placeholder UDF
**Assessment:** Architectural design choice. The DQM pipeline provides valueset data; standalone execution is out of scope. The placeholder already raises a clear error.

### QA8-005 (LOW): DEFERRED — ViewDef arbitrary resource types
**Assessment:** SQL-on-FHIR v2 spec does not mandate client-side validation. Low ROI.

## Test Results

- `fhir4ds/cql/tests/`: **3329 passed**, 55 skipped, 2 xpassed, 1 pre-existing failure (test_bp_profile_includes_component_columns — unrelated)
- Build: `hatch build` succeeded
- New tests: 7 in `test_include_errors.py`

**Why not parser fix:** An initial parser-level fix (adding `_try_parse_precision_of()` to the `ON_OR_BEFORE` branch) was correct for the reported bug but caused a DQM regression in CMS159 (100% → 53.7%). The CMS159 pattern `on or before day of end of "Measure Assessment Period"` changed routing from `cqlSameOrBefore(left, DATE_TRUNC_result)` to `cqlSameOrBeforeP(left, raw_right, 'day')`, which produced different results. The translator-level fix avoids this by operating on the AST before SQL translation.

**File:** `fhir4ds/cql/translator/expressions/_operators.py`

### QA7-002 (MEDIUM): RESOLVED — Count/Sum on flatten/union/except/intersect returns 1
**Status:** RESOLVED
**Root Cause:** `_unwrap_list_source()` only recognized `SQLArray` and `Distinct()` wrappers, not `flatten()`, `union`, `except`, or `intersect`. The aggregate handler also only checked `isinstance(source_sql, SQLArray)`.

**Fix:** Two changes in `_functions.py`:
1. Extended `_unwrap_list_source()` (line ~118) to detect `FunctionRef` (for flatten) and `BinaryExpression` with `union`/`except`/`intersect` operators.
## Pre-existing Test Failures (not introduced by this iteration)
- `test_choice_type_columns.py::test_bp_profile_includes_component_columns` (ARCH-004)
