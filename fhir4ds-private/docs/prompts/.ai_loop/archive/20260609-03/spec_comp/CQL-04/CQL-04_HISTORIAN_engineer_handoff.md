# Engineer Handoff - CQL-04 / HISTORIAN

## Triage

| Issue | Severity | Category | Status |
| --- | --- | --- | --- |
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |
| QA-002 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fixes

### QA-001

Root cause: `_infer_static_cql_type_for_logical_operand()` treated every `as` expression as the target type. For `as Any` and `as System.Any`, that erased a known non-Boolean source type before CQL logical operand validation.

Fix: In `fhir4ds/cql/translator/expressions/_operators.py`, logical type inference now unwraps `as Any` / `as System.Any` and validates the source expression. Boolean sources through `as Any` still pass.

Regression coverage: `test_cql_logical_operators_reject_non_boolean_as_any_operands()` and `test_cql_logical_operators_allow_boolean_as_any_operands()`.

### QA-002

Root cause: `_apply_singleton_from()` delegated CTE-backed query correlation to `_add_patient_id_correlation_to_exists()`, but during `translate_library()` no `patient_alias` exists yet. The helper returned the count/value SELECTs unchanged, so later Patient-scalar CTE generation wrapped uncorrelated singleton-from subqueries under `_patients AS _pt`.

Fix: In `fhir4ds/cql/translator/expressions/_functions.py`, the patient-correlation helper now falls back to the deferred `_pt` alias for Patient-context translation. This matches existing cte_manager alias expectations and adds `O.patient_id = _pt.patient_id` to singleton-from query count/value paths.

Regression coverage: `test_cql_logical_singleton_query_return_is_patient_correlated()`.

## Validation

- Fresh probe: `python3 .temp/qa/cql04_historian_probe.py` passed.
- Focused parity: `pytest -q fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py` passed `22 passed`.
- Broader focused subset passed `113 passed`.
- Full conformance passed `2822/2822`.

No C++ source changed, so no extension rebuild was required. The fresh probe still exercised the no-Python C++ logical surface for `logicalImplies` and list logical helpers.
