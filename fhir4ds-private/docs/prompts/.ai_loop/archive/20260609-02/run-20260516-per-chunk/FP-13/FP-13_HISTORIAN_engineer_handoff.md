# Engineer Handoff - FP-13 HISTORIAN

## Resolved Issues
- QA-001 HIGH: Fixed multi-item Date/Time `=`/`!=` semantics across Python fallback and native C++.
- QA-002 HIGH: Fixed native complex `~`/`!~` to recurse through child equivalence instead of raw JSON equality.

## Changes
- `fhir4ds/fhirpath/engine/invocations/equality.py`: collection length/order handling now happens before singleton Date/Time dispatch.
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`: `fpValuesEqual()` now uses `compareDateTimes()` for Date/Time equality; native equivalence now has recursive JSON object/array equivalence for complex values.
- `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py`: added native vs forced Python fallback regressions for multi-item temporal equality and complex equivalence.
- `extensions/fhirpath/test/sql/fhirpath.test`: added native SQL assertions for the same equality/equivalence cases.
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`: rebuilt and copied from `extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension`.
- `extensions/fhirpath/AGENTS.md`: documented the fixed fragile area.

## Validation
- `cmake --build build/release --config Release -j 8` from `extensions/fhirpath`: passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q`: 5 passed.
- `./build/release/test/unittest '*fhirpath*'` from `extensions/fhirpath`: all tests passed, 238 assertions.
- `python3 -m pytest fhir4ds/fhirpath -q`: 1204 passed, 1 existing warning.
- `python3 conformance/scripts/run_all.py | grep -E ...`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes For Architect
- The C++ recursive JSON equivalence intentionally applies unordered duplicate-aware matching for arrays, matching FHIRPath multi-item equivalence behavior and the existing Python fallback behavior for complex child lists.
- No new issues were discovered during remediation.
