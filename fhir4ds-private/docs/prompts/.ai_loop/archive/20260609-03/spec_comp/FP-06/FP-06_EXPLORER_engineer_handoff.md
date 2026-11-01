# Engineer Handoff: FP-06 EXPLORER

## Issues Resolved

### QA-001 MEDIUM

Fixed forced Python fallback corruption of numeric string literals inside chained `iif(...)` conversion expressions.

- Root cause: `FHIRPathEvaluator.compile()` globally applied the no-whitespace quoted Quantity normalization regex, which could rewrite ordinary strings such as `'1'` to `'1 '` when another quoted argument appeared later in the same function call.
- Fix: added string/comment/delimited-identifier aware normalization so quoted Quantity literal normalization only runs outside quoted text.
- Spec grounding: FHIRPath §5.5.1 and §5.5.3.

### QA-002 MEDIUM

Fixed forced Python fallback unary-minus leakage of `DescendingSortMarker` into ordinary conversion expressions.

- Root cause: `polarity_expression()` used the sort marker for all non-numeric unary `-` values.
- Fix: `sort_fn()` now sets a scoped `_sort_expression` flag while evaluating sort criteria; non-sort unary signs over non-numeric values now raise `FHIRPathError`, which public DuckDB wrappers convert to empty/NULL.
- Spec grounding: FHIRPath §5.5.3 and §6.8.

## Validation

- FP-06 EXPLORER probe: native 38/38, forced fallback 38/38, zero mismatches.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q`: 13 passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_new_functions.py fhir4ds/fhirpath/duckdb/tests/unit/test_new_functions.py -q`: 118 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q`: 8 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Files Changed

- `fhir4ds/fhirpath/duckdb/evaluator.py`
- `fhir4ds/fhirpath/engine/evaluators/__init__.py`
- `fhir4ds/fhirpath/engine/invocations/collections.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
- `fhir4ds/fhirpath/AGENTS.md`
- `.temp/qa/fp06_explorer_probe.py`
- `.temp/qa/fp06_explorer_native_after_fix.json`
- `.temp/qa/fp06_explorer_fallback_after_fix.json`
- `validation_summary.log`
