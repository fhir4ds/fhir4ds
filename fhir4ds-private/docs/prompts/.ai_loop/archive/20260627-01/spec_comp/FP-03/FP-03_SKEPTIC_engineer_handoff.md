# Engineer Handoff: FP-03 SKEPTIC

## Issues

- `QA-001` (`MEDIUM`, `RESOLVED`): native DuckDB/C++ evaluated
  `subsetOf()` and `supersetOf()` argument expressions against the root
  resource context inside scoped expressions, diverging from the Python
  fallback and FHIRPath scoped-function semantics.

## Root Cause

`extensions/fhirpath/src/fhirpath/evaluator.cpp::Evaluator::evalFunction()`
handled `subsetOf()` and `supersetOf()` by creating a root-resource context for
their single argument. That works for top-level calls such as
`nums.subsetOf(otherNums)`, but it is wrong inside `select()`,
`exists(criteria)`, and `all(criteria)`, where an argument like `right` must be
resolved relative to the current scoped item.

## Fix

Changed the native `subsetOf()` and `supersetOf()` branches to evaluate their
argument with `outer_input` when available, falling back to `input` otherwise.
This matches the existing native pattern for ordinary function arguments and
the forced Python fallback behavior.

## Files Changed

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp03_skeptic_fresh_probe.py`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`

## Validation

- `python3 .temp/qa/fp03_skeptic_fresh_probe.py` passed: 46 valid cases, 12
  invalid/error cases.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py -q`
  passed: 13/13.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"` passed: 740
  assertions in 2 test cases.
- Full conformance summary passed: ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, overall 2822/2822.

## New Issues

None.
