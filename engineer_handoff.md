# Engineer Handoff — Iteration 9 FIX Phase

## Summary

Iteration 9 addressed 4 QA issues. 2 FIXED, 2 DEFERRED.

## Issues

### QA9-001 (MEDIUM): FIXED — Undefined definition references fail fast
**Problem:** CQL referencing a non-existent definition name (e.g., `define X: NonExistentDef`) silently emitted `SQLIdentifier(name="NonExistentDef")`, producing confusing DuckDB parse errors at runtime.

**Fix:** In `_translate_identifier()` (line ~847), after all 7 resolution paths fail (alias, symbol table, let variables, Patient, codes, definitions, forward references), a `TranslationError` is now raised with the unresolved name and a list of available definitions.

**Guards:**
1. Only fires during real library translations (`_definition_names` or `expression_definitions` populated)
2. Skipped when library has includes — inlined function bodies may reference symbols from included libraries (codes, concepts, sub-definitions) that aren't in the main context

**Files changed:**
- `fhir4ds/cql/translator/expressions/_core.py` — Error at identifier fallback
- `fhir4ds/cql/tests/unit/test_undefined_reference_errors.py` — 4 tests
- `fhir4ds/cql/tests/integration/test_fluent_functions.py` — Updated error handling in 3 tests that were testing pre-existing broken behavior (verified fluent call, verified on retrieve, nested query scope)

### QA9-002 (MEDIUM): FIXED — Unknown function calls fail fast
**Problem:** CQL calling a non-existent function (e.g., `NonExistentFunc(1, 2)`) silently emitted `SQLFunctionCall(name="NonExistentFunc", ...)`, producing confusing DuckDB errors at runtime.

**Fix:** In `_translate_function_ref()` (line ~551), after all 6 resolution paths fail (pre-translate strategies, function registry, fluent functions, function inliner, special cases), a `TranslationError` is now raised with the function name and arity.

**Same guards as QA9-001:** Only fires during real library translations with no includes.

**Files changed:**
- `fhir4ds/cql/translator/expressions/_functions.py` — Error at function fallback
- `fhir4ds/cql/tests/unit/test_undefined_reference_errors.py` — 3 tests

### QA9-003 (LOW): DEFERRED — Invalid date literals not validated
**Assessment:** DuckDB catches invalid dates (e.g., `@2024-13-45`) at execution time with `Conversion Error: Could not convert string '2024-13-45' to DATE`. The error is clear enough for debugging. Translation-time validation would be nice but is low ROI — DuckDB already provides the guardrail.

### QA9-004 (LOW): DEFERRED — resolve() doesn't handle contained resource fragments
**Assessment:** The FHIRPath spec mentions contained resource resolution but it's effectively optional for analytical use cases. Current workaround (`contained.where(id = 'med1')`) is adequate. Adding fragment resolution is net-new functionality requiring new tests and documentation.

## Test Results

- `fhir4ds/cql/tests/`: **4220 passed**, 88 skipped, 2 xpassed, 2 pre-existing failures (test_bp_profile_includes_component_columns, test_full_conversion_example)
- New tests: 7 in `test_undefined_reference_errors.py`

## Conformance

```
ViewDefinition:    134/134   (100.0%)
FHIRPath (R4):     935/935   (100.0%)
CQL:               1626/1706 (95.3%)
DQM (QI Core):     42/46     (91.3%)
─────────────────────────────────────
OVERALL:           2737/2821 (97.0%) — AT BASELINE
```

## Pre-existing Test Failures (not introduced by this iteration)
- `test_choice_type_columns.py::test_bp_profile_includes_component_columns` (ARCH-004)
- `test_join_conversion.py::test_full_conversion_example` (patient alias naming change)
