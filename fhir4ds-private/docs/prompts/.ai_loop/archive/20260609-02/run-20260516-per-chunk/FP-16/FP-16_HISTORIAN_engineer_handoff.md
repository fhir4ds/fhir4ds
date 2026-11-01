# Engineer Handoff - FP-16 HISTORIAN

## Triage

| Issue | Severity | Category | Terminal State |
| --- | --- | --- | --- |
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fix Summary

QA-001 fixed native C++ collection operator equality for FHIR Quantity path values.

Root cause:
- `extensions/fhirpath/src/fhirpath/evaluator.cpp::fpValuesEqual()` is used by `|`, `union()`, `in`, `contains`, and related set-style helpers.
- It performed raw `JsonVal` equality before Quantity-like JSON values were materialized.
- Ordinary `=` had a separate pre-processing path that converted `Observation.valueQuantity` objects to `FPValue::Quantity`, so `value = component.value` returned true while `value in component.value` returned false for `1 cm` vs `10 mm`.

Surgical changes:
- Added `fpValueAsQuantity()` and called it inside `fpValuesEqual()` before raw JSON equality.
- The fix covers JSON-vs-JSON and JSON-vs-literal Quantity comparisons used by collection operators.
- Updated `fhir4ds/fhirpath/duckdb/operators.py::_values_equal()` to route direct helper membership checks through canonical Python FHIRPath `=` semantics.
- Added focused regression coverage for Quantity path membership/de-duplication and direct helper numeric equality.
- Rebuilt and copied the bundled native extension to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Spec grounding:
- FHIRPath §6.4.1 requires `|` to eliminate duplicate values using equality semantics.
- FHIRPath §6.4.2 defines `in` in terms of equality against an item in the right collection.
- FHIRPath §6.4.3 defines `contains` as the converse membership test.
- FHIRPath Quantity equality supports compatible unit comparison for the same dimension; the observed `=` result already confirmed the path pair was equal.

## Validation

Reproducer after fix:

```text
native_loaded=True, fallback_loaded=False
value in component.value                         OK
component.value contains value                   OK
value | component.value                          OK
value.union(component.value).count()             OK
1 'cm' in component.value                        OK
component.value contains 1 'cm'                  OK
component.value.union(1 'cm').count()            OK
```

Commands:

```bash
cmake --build build/release --config Release -j 8
# completed successfully

cp extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension

python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py::test_collection_operators_use_quantity_equality_for_fhir_quantity_paths -q
# 1 passed in 1.60s

python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py -q
# 116 passed in 3.09s

cd extensions/fhirpath && ./build/release/test/unittest "*fhirpath*" | tail -n 80
# All tests passed (250 assertions in 2 test cases)

python3 -m pytest fhir4ds/fhirpath -q
# 1221 passed, 1 warning in 32.43s

python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > .temp/qa/fp16_validation_summary.log && cat .temp/qa/fp16_validation_summary.log
# ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2822/2822
```

## New Issues

None.
