# Engineer Handoff - CQL-03 HISTORIAN

## Fixed

- `CQL03-HIST-001`: `ToQuantity` now binds numeric DuckDB inputs through the shared Python conformance helper in both native-loaded and forced Python fallback connections. JSON-shaped Quantity conversion checks now require a finite Decimal `value`.
- `CQL03-HIST-002`: `ToQuantity` now recognizes internal JSON-shaped Ratio values and returns the Quantity division of numerator by denominator.

## Implementation Notes

- Added `ToQuantity` to the CQL Python-preferred native conflict list because the bundled C++ symbol only exposes the legacy VARCHAR shape. No C++ source or bundled extension changed.
- Kept the fix scoped to CQL temporal/complex public DuckDB surfaces and parity tests.

## Verification

- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py -q` — 8 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests fhir4ds/cql/tests/unit fhir4ds/cql/tests/integration -q` — 1813 passed, 5 skipped.
- `python3 conformance/scripts/run_cql.py | grep -E "FAIL|ERROR|CQL|Suite|OVERALL|Passed|passed|failed|Total|%"` — 1706/1706 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM|passed|Summary"` — 2822/2822 overall.
