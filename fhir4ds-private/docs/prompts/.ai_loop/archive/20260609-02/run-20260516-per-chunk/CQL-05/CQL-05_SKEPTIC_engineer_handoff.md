# CQL-05 SKEPTIC Engineer Handoff

## Changes Made

- Added structural type target validation and support for `ListTypeSpecifier`/`IntervalTypeSpecifier` in `is` and `as`.
- Extended static structural inference for aliases, List/Interval, Ratio, Date, DateTime, Time, and conversion/constructor functions.
- Preserved `as Quantity` as a Quantity-shaped SQL expression with `parse_quantity(...)` and `result_type = "Quantity"`.
- Preserved `CQLMessage(...)` through structural `as Interval<T>` so strict error messages are not wrapped in FHIRPath type probes.
- Let dynamic FHIR `as Concept`/`as Code` values continue to runtime matching while keeping static clinical mismatches strict.
- Routed `ParameterPlaceholder` SQL CASE sources through FHIRPath property navigation.
- Added a quantity comparison fallback for scalar optimized CTE values, gated so JSON Quantity objects still rely on unit-aware `quantity_compare`.
- Added regression coverage in `test_structural_type_parity.py` and `test_gap_remediation.py`, including both native-loaded and forced Python fallback DuckDB registrations.

## Files Touched

- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_query.py`
- `fhir4ds/cql/translator/expressions/_property.py`
- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`
- `fhir4ds/cql/tests/unit/test_gap_remediation.py`

## Regression Notes

- CMS0334 bad-unit fixture is now covered directly: `37 cm` does not satisfy `>= 37 'weeks'`.
- CMS165 remains covered through the targeted DQM subset, proving scalar optimized quantity CTE comparison still works.
- CMS1218 SQL CASE placeholder navigation is covered by a focused unit regression.
