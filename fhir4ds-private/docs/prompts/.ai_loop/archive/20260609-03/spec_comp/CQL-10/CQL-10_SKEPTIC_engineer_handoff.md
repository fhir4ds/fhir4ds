# Engineer Handoff: CQL-10 SKEPTIC

## Fixed

`QA-001` HIGH: Python fallback Quantity arithmetic accepted malformed JSON numeric evidence.

Root cause: `fhir4ds/cql/duckdb/udf/quantity.py::_parse_quantity` preserved string and Boolean `value` members. Quantity helpers such as `quantityValue`, `quantityAdd`, `quantityDivide`, and translated dynamic FHIR Quantity arithmetic then coerced those through `float()`, while native C++ returned SQL NULL.

Fix:
- Normalize non-numeric Quantity `value` members to `NULL` in `_parse_quantity`.
- Guard `_quantity_to_pint` against bool/string values before numeric conversion.
- Add direct and translated arithmetic regression coverage to `test_arithmetic_operator_parity.py`.

## Validation

- `.temp/qa/cql10_skeptic_probe.py`: PASS
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py -q`: 6 passed
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py -k 'Arithmetic' -q`: 348 passed
- `python3 conformance/scripts/run_all.py | grep ...`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822

## Changed Files

- `fhir4ds/cql/duckdb/udf/quantity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py`
- `.temp/qa/cql10_skeptic_probe.py`
