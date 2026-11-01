# Engineer Handoff - FP-14 HISTORIAN

## Issue Status

- `QA-001`: RESOLVED

## Fix

Native C++ comparison preprocessing now recognizes FHIR JSON Quantity path results as quantity-like before applying comparison/equality operators. The new `isQuantityLike()` helper covers:

- Existing `FPValue::Quantity` values.
- JSON values with FHIR `Quantity` or Quantity-subtype metadata.
- Structural JSON Quantity objects containing `value` plus `code` or `unit`.

This lets both operands in expressions such as `value > component.value` and `valueQuantity <= component.valueQuantity` materialize as `FPValue::Quantity` before UCUM-compatible comparison.

## Files Touched

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

## Verification

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q` -> 3 passed
- `./build/release/test/unittest "*fhirpath*"` -> 250 assertions passed
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests fhir4ds/fhirpath/tests/unit -q` -> 1207 passed, 1 existing warning
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822

## Notes

The spec basis is FHIRPath v2.0.0 Section 6.2 comparison: comparison operands must be the same type or implicitly convertible, and the section explicitly includes compatible-unit Quantity comparisons. No new issues were discovered during remediation.
