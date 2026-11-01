# Engineer Handoff: CQL-13 SKEPTIC

Resolved `QA-001` as a spec-grounded date/time duration fix.

Root cause: `cqlDurationBetween` used the full high boundary of an imprecise end operand for uncertainty max calculation. That is appropriate for `cqlDifferenceBetween`, which counts crossed boundaries, but can overcount `duration` whole calendar periods. The concrete failure was `months between @2012-01-02 and @2012`, which became `[0, 11]` instead of the current CQL Reference `[0, 10]`.

Fix:
- Added `_duration_high_boundary()` in `fhir4ds/cql/duckdb/udf/datetime.py` and used it only for `cqlDurationBetween` max uncertainty.
- Added `DurationHighBoundaryValue()` in `extensions/cql/src/cql_extension.cpp` and used it only in `CqlDurationBetweenString`.
- Preserved `cqlDifferenceBetween` full-boundary behavior.
- Updated parity coverage in `test_datetime_part1_parity.py` and no-Python C++ coverage in `test_wasm_cpp_surface.py`.
- Rebuilt `extensions/cql/build/release/extension/cql/cql.duckdb_extension` and copied it to `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.

Validation:
- `.temp/qa/cql13_skeptic_probe.py`: PASS.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q`: 16 passed.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_datetime_operators -q`: 246 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
