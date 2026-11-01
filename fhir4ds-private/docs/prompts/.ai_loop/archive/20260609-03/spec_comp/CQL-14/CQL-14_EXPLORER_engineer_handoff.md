# Engineer Handoff: CQL-14 EXPLORER

## Fixed

- `QA-001` HIGH: DateTime timezone normalization now applies only for hour-or-finer precision comparisons. Year/month/day precision compares local DateTime components, matching CQL Reference v1.5.3.
- `QA-002` HIGH: offset-bearing Time values no longer flow through DateTime timezone normalization in Python fallback, preventing midnight underflow and restoring parity with native C++ behavior.

## Implementation

- Updated Python fallback temporal comparison normalization gates in `fhir4ds/cql/duckdb/udf/datetime.py`.
- Updated no-Python/native C++ `CompareTemporal` normalization gates in `extensions/cql/src/cql_extension.cpp`.
- Rebuilt and copied `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.
- Added regression coverage in `test_datetime_part2_parity.py`, `test_wasm_cpp_surface.py`, and `.temp/qa/cql14_explorer_probe.py`.
- Updated root and CQL extension `AGENTS.md` with the normalization invariant.

## Validation

- `.temp/qa/cql14_explorer_probe.py`: PASS
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q`: 11 passed
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_datetime_operators -q`: 246 passed
- `python3 conformance/scripts/run_all.py | grep ...`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822
