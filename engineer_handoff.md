# Engineer Handoff — Iteration 5 FIX Phase

## Fixes Applied

### QA5-004 (HIGH): CQL `same or before/after <precision> of` emits string equality
**Files:** `fhir4ds/cql/translator/expressions/_temporal_comparisons.py`, `fhir4ds/cql/translator/expressions/__init__.py`, `fhir4ds/cql/translator/inference.py`
**Root cause:** The CQL parser emits two operator string forms depending on source syntax:
- `"same month or before"` — from `same month or before X`
- `"same or before month of"` — from `same or before month of X`

`_translate_same_operator()` only matched the first form. The second form fell through to a fallback `SQLBinaryOp(operator="=")`, silently producing string equality instead of temporal comparison.
**Fix:**
1. Added alternate patterns (`f"same or before {precision} of"`, `f"same or after {precision} of"`, `f"same as {precision} of"`) to the precision loop in `_translate_same_operator()`.
2. Added `startswith('same ')` fallback in three inference functions (`_is_forward_ref_boolean`, `_infer_row_shape`, `_infer_cql_type`) to correctly identify precision-qualified same operators as boolean/scalar.
**Classification:** BUG — silently wrong results for standard CQL syntax (CQL §19.15-16)

### QA5-001: DEFERRED — Not a bug
The QA report cited FHIRPath §5.3 for returning empty on incompatible type comparison. Investigation showed:
- FHIRPath §6.6 specifies comparison of incompatible types is a **type error** (not empty)
- Official FHIRPath R4 conformance tests (`testLiteralDecimalLessThanInvalid`, `testPrecedence3`) expect errors
- Current Python evaluator behavior (throwing `FHIRPathError`) is **correct**

### QA5-002: NOT REPRODUCIBLE
Tested `@2020-01-01T10:00:00`, `@2020-01-01T10:00:00Z`, and 7 other dateTime formats. All parse correctly. The ANTLR grammar, lexer, and Python `dateTimeRE` regex all handle time components.

### QA5-003: NOT REPRODUCIBLE
Tested `'a' & 'b'`, `'hello' & ' ' & 'world'`, etc. All evaluate correctly to expected results.

## Conformance

| Suite | Passed | Total | Rate |
|-------|--------|-------|------|
| ViewDefinition | 134 | 134 | 100.0% |
| FHIRPath (R4) | 935 | 935 | 100.0% |
| CQL | 1706 | 1706 | 100.0% |
| DQM (QI Core 2025) | 42 | 46 | 91.3% |
| **OVERALL** | **2817** | **2821** | **99.9%** |

No regression from baseline. Unit tests: 3806 passed, 1 pre-existing failure.

## Pre-existing Test Failures (not introduced by this iteration)
- `test_choice_type_columns.py::test_bp_profile_includes_component_columns` (ARCH-004)
