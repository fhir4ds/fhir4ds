# Review 15 Remediation

Milestone review `review-15.md` found one backend parity issue after chunks FP-11 through FP-15.

## Finding Remediated

- `REV-001` MEDIUM: forced Python fallback `fhirpath_is_valid()` treated sample-resource evaluation errors as invalid expressions. That made syntactically and semantically valid expressions that evaluate to an empty result, such as `'10' > 2`, `'x' + 1`, and `true < 1`, report `false` while the native C++ extension reported `true`. Fixed the fallback validation path to distinguish valid empty-result expression errors from true invalid-expression cases, while keeping malformed type specifiers, wrong type-function arity, and malformed temporal literals invalid.

## Regression Coverage

- `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py::test_valid_empty_result_expressions_keep_is_valid_parity`

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q --tb=short` passed: 5 tests.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py::test_malformed_temporal_literal_shapes_are_invalid_in_both_backends fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q --tb=short` passed: 6 tests.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py fhir4ds/fhirpath/duckdb/tests/unit/test_math.py -q --tb=short` passed: 134 tests.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath -q --tb=short` passed: 1217 tests, 1 existing warning.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
