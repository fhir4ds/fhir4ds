# Engineer Handoff — Iteration 4 FIX Phase

## Fixes Applied

### QA4-001 (MEDIUM): FHIRPath RecursionError at ~245 chained calls
**File:** `fhir4ds/fhirpath/engine/__init__.py`
**Root cause:** `do_eval()` recursively dispatches evaluators without depth guard. ~245 chained method calls exhausts Python's 1000-frame stack (~4 frames/node).
**Fix:** Wrapped evaluator call in `try/except RecursionError`, raising `FHIRPathEvaluationError` with clear message. Spec is silent on depth limits; controlled error is sufficient.
**Classification:** ROBUSTNESS (not spec violation)

### QA4-002 (MEDIUM): CQL RecursionError on ~66 nested parentheses
**File:** `fhir4ds/cql/parser/parser.py`
**Root cause:** Recursive descent parser's `_parse_parenthesized_or_tuple()` → `parse_expression()` chain uses ~15 frames per nesting level. 66 levels exhausts stack.
**Fix:** Wrapped `parse_expression()` call in `try/except RecursionError`, raising `ParseError` with clear message.
**Classification:** ROBUSTNESS (not spec violation)

### QA4-003 (MEDIUM): MeasureParser accepts wrong resourceType
**File:** `fhir4ds/dqm/parser.py`
**Root cause:** `parse()` checked for Bundle extraction but never validated `resourceType == "Measure"` after extraction or on direct input.
**Fix:** Added `if rt != "Measure": raise MeasureParseError(...)` after Bundle extraction, before processing.
**Classification:** BUG (FHIR R4 mandates resourceType validation)

### QA4-004 (LOW): translate_cql(None) leaks TypeError
**File:** `fhir4ds/cql/translator/__init__.py`
**Root cause:** No input validation — `None` propagated into parser which called `len(None)`.
**Fix:** Added `if not isinstance(cql_text, str) or not cql_text.strip(): raise ValueError(...)` at function entry.
**Classification:** BUG (API contract violation)

## Conformance

| Suite | Passed | Total | Rate |
|-------|--------|-------|------|
| ViewDefinition | 134 | 134 | 100.0% |
| FHIRPath (R4) | 935 | 935 | 100.0% |
| CQL | 1706 | 1706 | 100.0% |
| DQM (QI Core 2025) | 42 | 46 | 91.3% |
| **OVERALL** | **2817** | **2821** | **99.9%** |

No regression from baseline.

## Pre-existing Test Failures (not introduced by this iteration)
- `test_choice_type_columns.py::test_bp_profile_includes_component_columns` (ARCH-004)
- `test_join_conversion.py::test_full_conversion_example` (stale alias from QA-001 fix)
