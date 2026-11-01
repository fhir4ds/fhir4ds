# Engineer Handoff - FP-10 EXPLORER

## Triage

| Issue | Severity | Category | Status |
|---|---|---|---|
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |
| QA-002 | MEDIUM | BINARY_DRIFT | RESOLVED |

## Fixes

`QA-001`: Native C++ regex evaluation used `std::regex` over UTF-8 bytes. The prior DOTALL handling replaced unescaped `.` with a byte-sized class, so `é.matches('.')` returned false and `é.replaceMatches('.', 'x')` produced two replacements. Added `normalizeFHIRPathRegex()` in `extensions/fhirpath/src/fhirpath/evaluator.cpp` to convert unescaped dots outside character classes into a UTF-8 code-point atom before calling `std::regex`.

`QA-002`: The native source already had Unicode case mapping for `ß` and Greek final sigma, but the packaged extension binary was stale. Rebuilt `extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension` and copied it to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

## Tests Added

- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`: native vs forced Python fallback parity for `é`/`😀` regex dot behavior and stale Unicode case-mapping regressions.
- `extensions/fhirpath/test/sql/fhirpath.test`: native SQL assertions for Unicode regex dot behavior.

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/fp10_explorer_probe.py`: mismatches=0.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py -q`: 2 passed.
- `extensions/fhirpath/build/release/test/unittest '*fhirpath*'`: 188 assertions passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_string.py fhir4ds/fhirpath/tests/unit/test_new_functions.py -q`: 172 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep ...`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
