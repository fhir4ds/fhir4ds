# Architect Handoff - FP-16 HISTORIAN

## Structural Health

FP-16 HISTORIAN is structurally clean after remediation. The correct architecture for §6.4 is that collection operators do not own separate comparison semantics; native C++ set-style behavior routes through `fpValuesEqual()`, Python core routes through canonical equality invocations, and public DuckDB parity is verified against both native and forced Python fallback paths.

The original defect was a helper-boundary drift: ordinary native `=` materialized Quantity-like JSON path values, but the shared native collection helper compared raw JSON first. The fix is appropriately general because `fpValueAsQuantity()` sits inside `fpValuesEqual()`, covering `|`, `union()`, `in`, `contains`, `intersect()`, `exclude()`, `distinct()`, and other users of that helper rather than special-casing the QA expression. The adjacent Python direct helper was also aligned with canonical FHIRPath equality, reducing parallel logic.

## QA Audit

QA was sufficient. It did not only test happy paths: it covered empty and multi-item operands, temporal equality, structural object equality, numeric equality, real FHIR Quantity paths, and native-vs-forced-fallback public UDF parity. No `RETRY_QA` flag is warranted.

## Issue Summary

| Status | Count |
| --- | ---: |
| VERIFIED | 1 |
| Open / Non-terminal | 0 |

## Validation Reviewed

```bash
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py::test_collection_operators_use_quantity_equality_for_fhir_quantity_paths -q
# 1 passed

python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py -q
# 116 passed

cd extensions/fhirpath && ./build/release/test/unittest "*fhirpath*" | tail -n 80
# 250 assertions passed

python3 -m pytest fhir4ds/fhirpath -q
# 1221 passed, 1 existing warning

python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > .temp/qa/fp16_validation_summary.log && cat .temp/qa/fp16_validation_summary.log
# ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2822/2822
```

## Recommended Fix Order

No further remediation required for this chunk. Continue to clean exit.
