# Engineer Handoff - FP-16 SKEPTIC

Resolved `QA-FP16-SKEPTIC-001` in
`fhir4ds/fhirpath/duckdb/udf.py`. Root cause was fallback validation relying
on sparse sample evaluation for collection membership expressions, so constant
multi-item literal unions on the singleton side could be hidden by absent
resource paths.

The fix adds a narrow static precheck for infix membership operators:
`in` checks the left operand and infix `contains` checks the right operand.
The precheck reuses literal-union effective item logic, so duplicate
elimination, numeric equality, and empty collection removal are honored before
cardinality validation. Method-call `s.contains(...)` remains handled by the
string-search validator.

Regression coverage was added in
`fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py`
for native/fallback invalid literal unions and valid duplicate/empty union
cases.

Validation:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py -q`
  passed 16/16.
- `python3 .temp/qa/fp16_skeptic_probe.py` reported `FAILURES 0`.
- Full conformance summary: ViewDefinition 134/134, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, overall 2822/2822.
