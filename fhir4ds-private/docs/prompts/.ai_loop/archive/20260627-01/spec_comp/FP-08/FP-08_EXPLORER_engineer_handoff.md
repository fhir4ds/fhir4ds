# Engineer Handoff - FP-08 EXPLORER

## Issue

- `QA-001` MEDIUM SPEC_VIOLATION: §5.5.8 `toString()` over resource-backed
  JSON Decimal values emitted scientific notation (`1e-06`, native `1e+15`)
  instead of decimal digit notation. The fresh probe also covered native
  max-Long `toQuantity().toString()` precision loss through `double`.

## Root Cause

Python fallback `to_string()` formatted resource-backed float primitives with
`str(float)`, which can produce exponent notation. Native C++ `jsonValToString`
formatted JSON real values with default stream formatting, and native
`fn_toQuantity()` converted Integer/Long inputs to Quantity through `double`
without preserving integer source text for string output.

## Fix

- Python fallback now converts float values through `Decimal(str(value))` and
  formats Decimal values with fixed decimal notation in `to_string()`.
- Native C++ now uses `formatDecimalNumber()` for Decimal/JSON real
  stringification and preserves integer source text when Integer/Long values
  become Quantity values.
- Added permanent native/fallback parity coverage in
  `test_conversion_parity.py`.
- Added native sqllogictest assertions in `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied the bundled `fhirpath.duckdb_extension`.

## Validation

- `python3 .temp/qa/fp08_explorer_fresh_probe.py` passed, 21 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_empty_quantity_unit_parity.py -q` passed, 24/24.
- `cmake --build extensions/fhirpath/build/release --config Release -j 8` passed after the documented forward-declaration fix.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"` passed, 806 assertions.
- `git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp08_explorer_fresh_probe.py` passed.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Extension hashes match across build, repository, and package bundle.

## State

`QA-001` is `RESOLVED`. Proceed to ARCHITECT.
