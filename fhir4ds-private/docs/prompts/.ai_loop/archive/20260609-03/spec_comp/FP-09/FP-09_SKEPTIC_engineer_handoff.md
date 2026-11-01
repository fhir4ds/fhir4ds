# Engineer Handoff — FP-09 SKEPTIC

## Issues Resolved

### QA-001 HIGH

Native C++ ignored extra arguments for FP-09 string-search functions and reported malformed arity as valid.

Root cause:

- `Evaluator::evalFunction` enforced exact arity for prior chunks, but not for `indexOf`, `substring`, `startsWith`, `endsWith`, or string-function `contains`.
- The dispatcher evaluated `node.children[0]` before any §5.6 arity guard, so missing arguments were caught only as row-resilient empty results and extra arguments were ignored.

Fix:

- Added exact native arity checks:
  - `indexOf`, `startsWith`, `endsWith`, `contains`: exactly 1 argument.
  - `substring`: 1 or 2 arguments.
- Added native sqllogictest and Python parity coverage.

### QA-002 MEDIUM

Native C++ returned empty but `fhirpath_is_valid=true` for constant wrong-type §5.6 calls.

Root cause:

- Native string-search helper functions returned empty for concrete wrong input/argument types instead of throwing `FHIRPathSpecError`.
- Empty-input short-circuiting could run before argument type checks, allowing sparse validation input to hide malformed parameter expressions.
- Forced Python fallback validation similarly needed a static FP-09 arity/literal-argument precheck because its minimal Patient validation resource can make tested paths empty.

Fix:

- Native helpers now throw `FHIRPathSpecError` for:
  - Non-String search terms.
  - Non-Integer `substring` start/length parameters.
  - Concrete non-String input values.
  - Multi-item argument collections.
- Empty propagation is preserved for empty input, empty search argument, and empty optional `substring` length.
- Forced Python fallback `fhirpath_is_valid()` now statically rejects FP-09 malformed arity and obvious literal argument type errors.

## Validation

- `.temp/qa/fp09_skeptic_probe_after_fix.log`: 35 cases, 0 native/fallback mismatches, 0 expectation failures.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py -q`: 4 passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath`: 436 assertions passed.
- `python3 conformance/scripts/run_all.py | grep ...`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Files Touched

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/udf.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.temp/qa/fp09_skeptic_probe.py`
- `.temp/qa/fp09_skeptic_probe.log`
- `.temp/qa/fp09_skeptic_probe_after_fix.log`
- `validation_summary.log`
