# Engineer Handoff - FP-16 EXPLORER

Resolved QA-001. Python core `collections.inn()` now raises `FHIRPathError` when the left operand has multiple items, and `collections.contains()` raises when the right operand has multiple items. Native C++ `Evaluator::evalBinaryOp()` now throws `FHIRPathSpecError` for the same §6.4 singleton violations.

Public DuckDB behavior remains intentionally resilient: native C++ materialization catches `FHIRPathSpecError`, and Python fallback UDFs catch `FHIRPathError` outside strict/core direct evaluation, so public `fhirpath`, `fhirpath_json`, and `fhirpath_bool` still return empty/NULL for `a in one` and `one contains a`.

Regression coverage added:
- `fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py::test_membership_operators_reject_multi_item_singleton_operand`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py::test_membership_singleton_errors_are_resilient_in_public_duckdb_udfs`

Native extension was rebuilt with `cmake --build build/release --config Release -j 8` from `extensions/fhirpath`, then copied to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Validation:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py::test_membership_operators_reject_multi_item_singleton_operand -q` passed: 8 tests.
- `./build/release/test/unittest '*fhirpath*'` from `extensions/fhirpath` passed: 250 assertions in 2 test cases.
- `python3 conformance/scripts/run_fhirpath_r4.py` passed; parsed report shows FHIRPath R4 935/935, failures=0.
- `python3 -m pytest fhir4ds/fhirpath -q` passed: 1223 tests, 1 existing warning.
