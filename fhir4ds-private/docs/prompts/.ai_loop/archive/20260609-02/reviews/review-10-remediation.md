# Review 10 Remediation

Milestone review `review-10.md` found three issues after chunks FP-06 through FP-10.

## Findings Remediated

- `REV-001` HIGH: native C++ and direct Python helper regex paths lacked the core ReDoS guard. Fixed native regex validation to reject overlong patterns and common catastrophic backtracking shapes before `std::regex` compilation, while validating the original user pattern before UTF-8 dot normalization. Added the same guard to direct string helpers.
- `REV-002` MEDIUM: direct conversion helpers drifted from FP-06 through FP-08 semantics. Fixed direct helper `to_date()`, `to_time()`, and `to_quantity()` to reject malformed DateTime truncation, timezone-bearing Time strings, leading-whitespace/empty-unit/bare-duration quantity strings, and incompatible target units.

## Deferred

- `REV-003` MEDIUM: native type reflection still embeds FHIR model metadata in `evaluator.cpp`. This requires generated C++ metadata from canonical FHIR model artifacts plus broad type/reflection parity coverage, so it is recorded as deferred architecture work rather than a safe milestone patch.

## Regression Coverage

- `extensions/fhirpath/test/sql/fhirpath.test` covers native ReDoS guard behavior for `matches()` and `replaceMatches()`.
- `fhir4ds/fhirpath/duckdb/tests/unit/test_string.py` covers direct helper ReDoS rejection.
- `fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py` covers strict direct helper conversion behavior.
- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py` covers native/fallback regex guard parity.

## Validation

- `cmake --build build/release --config Release -j 8` from `extensions/fhirpath` passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath` passed: 192 assertions.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_string.py fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q --tb=short` passed: 230 tests.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests -q --tb=short` passed: 1024 tests, 1 existing warning.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath -q --tb=short` passed: 1193 tests, 1 existing warning.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
