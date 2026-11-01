# Review 5 Remediation

Milestone review `review-5.md` found two confirmed scope-leak regressions after chunks FP-01 through FP-05.

## Findings Remediated

- `REV-001` HIGH: Python fallback `all(criteria)` leaked `$index` after criteria evaluation. Fixed by saving and restoring the previous `$index` value in `fhir4ds/fhirpath/engine/invocations/existence.py`.
- `REV-002` MEDIUM: Native C++ `where(criteria)` leaked `defineVariable()` state into later chained expressions. Fixed by saving and restoring `defined_variables_` around each criteria evaluation in `extensions/fhirpath/src/fhirpath/evaluator.cpp`.

## Regression Coverage

- `fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py::test_all_criteria_restores_index_context_in_fallback`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py::test_where_define_variable_scope_does_not_leak_in_native`

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` -> 14 passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath` -> 114 assertions passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath -q` -> 1166 passed, 1 existing warning.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

