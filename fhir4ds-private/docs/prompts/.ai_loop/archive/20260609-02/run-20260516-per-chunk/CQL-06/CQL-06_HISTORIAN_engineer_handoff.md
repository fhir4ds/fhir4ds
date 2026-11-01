# Engineer Handoff - CQL-06 HISTORIAN

## Fixed Issue

`QA-001` resolved. `ConvertsToDecimal` now rejects decimal strings that cannot be represented by the current DuckDB `DECIMAL(38, 8)` target, and `ToDecimal` no longer rounds string inputs with more than eight fractional digits.

## Files Changed

- `fhir4ds/cql/duckdb/udf/conversion.py`
- `fhir4ds/cql/duckdb/macros/conversion.py`
- `fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py`

## Validation

- Direct HISTORIAN matrix: 32 conversion-check cases passed on native-loaded and forced Python fallback registrations.
- Focused parity pytest: 13 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No native C++ source changed in this personality.
