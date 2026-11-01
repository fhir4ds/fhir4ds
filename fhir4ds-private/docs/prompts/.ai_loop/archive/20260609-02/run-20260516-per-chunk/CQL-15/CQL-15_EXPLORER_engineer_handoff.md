# Engineer Handoff - CQL-15 EXPLORER

## Triage

| Issue | Severity | Category | Status |
| --- | --- | --- | --- |
| `QA-CQL15-EXPLORER-001` | HIGH | SPEC_VIOLATION | VERIFIED |
| `QA-CQL15-EXPLORER-002` | MEDIUM | SPEC_VIOLATION | VERIFIED |

## Fixes

1. Preserved Quantity shape through Python interval parsing and comparison.
   - Added Quantity-bound helpers in `fhir4ds/cql/duckdb/udf/interval.py`.
   - `_normalize_for_compare()` now converts compatible Quantity operands through the existing Quantity/Pint helper path instead of comparing raw magnitudes.
   - Open-bound successor/predecessor handling preserves Quantity JSON shape.

2. Aligned no-Python C++ interval Quantity comparison.
   - `extensions/cql/src/cql/interval.cpp::BoundValue::compare()` now dispatches Quantity comparisons through `cql::quantity_compare`.
   - Rebuilt `extensions/cql/build/release/extension/cql/cql.duckdb_extension`.
   - Copied the rebuilt binary to `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`; SHA-256 is `34bd8499cc62ef5891004081531ce74e697407f0a19516a7ffec4410690fc4e6`.

3. Preserved interval identity for nested set-operation results.
   - `fhir4ds/cql/translator/expressions/_temporal_intervals.py::_is_fhir_interval_expression()` now treats `intervalExcept`, `intervalIntersect`, and `intervalUnion` as interval-valued SQL expressions.
   - Added translated execution coverage for `(Interval[1, 10] except Interval[1, 4]) contains 5`.

## Tests Added

- `test_cql_interval_quantity_contains_uses_unit_aware_comparison()` covers direct and translated Quantity interval contains/includes on forced Python fallback, native-loaded registration, and no-Python C++.
- Existing Interval Part 1 parity coverage now includes nested `except` under `contains`.

## Verification Completed

- `./build/release/test/unittest '*cql*'` - 694 assertions passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py -q` - 9 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py -q` - 15 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py::test_cql_browser_interval_and_boundary_udfs_run_without_python_fallback -q` - 1 passed.
- `.temp/qa/cql15_explorer_probe.py` - fixed cases passed across all three surfaces.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_interval_operators -q --tb=short` - 421 passed after regression hardening.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_cql.py` - CQL 1706/1706 after regression hardening.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` - overall 2822/2822.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/ --tb=short` - 7195 passed, 5 skipped, 9 warnings.

The first full conformance run exposed a DQM regression in Quantity interval width/collapse handling; that was fixed before the final conformance and full pytest runs above.
