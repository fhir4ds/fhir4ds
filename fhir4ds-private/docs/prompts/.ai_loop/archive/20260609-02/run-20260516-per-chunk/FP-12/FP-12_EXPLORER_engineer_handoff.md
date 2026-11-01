# Engineer Handoff - FP-12 EXPLORER

## Issue Status

- QA-001 HIGH: RESOLVED

## Fix

Native C++ current-time functions now share one cached timestamp per
`Evaluator::evaluate()` call:
- Added `Evaluator::currentTime()`.
- Reset the cache at the start of `Evaluator::evaluate()`.
- Routed `now()`, `today()`, and `timeOfDay()` through the cached value.

This implements FHIRPath N1 section 5.9.2's determinism requirement that
current-time functions return the same value regardless of how many times they
are evaluated within one expression.

## Regression Coverage

Added `test_current_time_functions_are_stable_within_native_expression` to
`fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`. It
compares native C++ DuckDB behavior with the forced Python fallback on a long
single expression that invokes `now()` twice.

## Validation

- `cmake --build build/release --config Release -j 8`
- Copied rebuilt `extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension` to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py -q` -> 3 passed
- `./build/release/test/unittest "*fhirpath*"` -> 226 assertions passed
- Native/fallback reproducer shell check -> both true
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_new_functions.py fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py -q` -> 73 passed
- `python3 -m pytest fhir4ds/fhirpath -q` -> 1200 passed, 1 existing warning
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822

## Files Changed By This Remediation

- `extensions/fhirpath/src/fhirpath/evaluator.hpp`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`
- `AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
