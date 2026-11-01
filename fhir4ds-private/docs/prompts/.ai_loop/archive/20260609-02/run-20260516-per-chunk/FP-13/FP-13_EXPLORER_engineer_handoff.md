# Engineer Handoff - FP-13 EXPLORER

## Issue Status
- `QA-001` HIGH -> `RESOLVED`.

## Root Cause
- Native C++ equality treated all non-Time temporal primitives as comparable through `compareDateTimes()`.
- This allowed `Date` and partial `DateTime` values with the same populated components to compare equal/equivalent, e.g. `@2012 = @2012T`.
- The Python fallback already matched the spec shape: empty for `=`/`!=`, false/true for `~`/`!~`.

## Fix
- Added `isDateVsDateTimePair()` in `extensions/fhirpath/src/fhirpath/evaluator.cpp`.
- Applied the guard in:
  - `fpValuesEqual()` helper.
  - singleton native `=`, `!=`, `~`, `!~` dispatch.
  - multi-item ordered equality dispatch.
  - multi-item equivalence item matching.
- Rebuilt the native extension and copied it to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

## Tests Added
- `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py`
  - native vs forced Python fallback parity for singleton and multi-item `Date` vs `DateTime` equality/equivalence.
- `extensions/fhirpath/test/sql/fhirpath.test`
  - native SQL assertions for `@2012 = @2012T`, `!=`, `~`, `!~`, and multi-item cases.

## Validation
- Focused native/fallback repro: fixed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q --tb=short` -> 6 passed.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"` -> 250 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath -q --tb=short` -> 1205 passed, 1 existing warning.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> overall 2822/2822, 100%.

## Notes for Architect
- The fix is narrow and spec-grounded in FHIRPath §6.1 same-type equality/equivalence.
- Main audit point: confirm every native equality path now handles `Date` vs `DateTime`, including helper use by collection/set semantics.
