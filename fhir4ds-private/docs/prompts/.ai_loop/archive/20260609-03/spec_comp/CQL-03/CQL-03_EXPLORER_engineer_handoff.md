# Engineer Handoff — CQL-03 EXPLORER

Resolved issue:
- `QA-001` HIGH, spec violation.

Root cause:
- Temporal constructor translation rejected non-Integer literal components, but expression-valued components were passed directly into `printf`, range comparisons, and timezone `TRY_CAST` paths.
- DuckDB then coerced Boolean/String expressions in some Date/DateTime paths or produced invalid SQL precedence/binder failures in Time paths.

Fix:
- Added static temporal component inference for Boolean, String, function, type assertion, comparison, and logical expression shapes in `_functions.py`.
- Added runtime DuckDB `typeof(...)` guards in `_temporal_components.py` so multi-component Date, DateTime, and Time constructors only format Integer component expressions, and DateTime timezoneOffset only formats numeric expressions.
- Wrapped formatted constructor arguments with guarded `TRY_CAST` to keep runtime invalid rows NULL-resilient instead of leaking malformed SQL or coerced values.
- Preserved existing `date from DateTime` lowering through `ToDate(...)`.

Tests added:
- `test_temporal_constructors_reject_non_integer_expression_components` in `test_temporal_complex_parity.py`.
- Fresh probe `.temp/qa/cql03_explorer_probe.py`.

Validation:
- `python3 .temp/qa/cql03_explorer_probe.py`
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py fhir4ds/cql/duckdb/tests/integration/test_datetime_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py -q` — 30 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py fhir4ds/cql/duckdb/tests/test_ratio_udfs.py fhir4ds/cql/duckdb/tests/test_quantity_udf.py -q` — 94 passed.
- `extensions/cql/build/release/test/unittest "*cql*"` — 782 assertions passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > validation_summary.log && cat validation_summary.log` — 2822/2822.
