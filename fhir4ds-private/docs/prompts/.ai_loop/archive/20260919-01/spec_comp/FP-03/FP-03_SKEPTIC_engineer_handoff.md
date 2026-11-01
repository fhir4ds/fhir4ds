# Engineer Handoff — FP-03 SKEPTIC (iteration 1, 2026-08-17)

## Triage
| Issue | Category | Severity | Triage |
|---|---|---|---|
| QA-001 | SPEC_VIOLATION (§6.2 error signaling via §5.1 iteration criteria) | HIGH | CONFIRMED → RESOLVED |
| QA-002 | PARITY (time-string ordering coercion) | MEDIUM | CONFIRMED → RESOLVED |

## QA-001 — native comparison type-mismatch swallow (HIGH)
- **Root cause**: `extensions/fhirpath/src/fhirpath/evaluator.cpp` `evalBinaryOp`
  comparison branch returned `{}` at the two terminal incompatible-type sites
  ("one numeric, one not" and the catch-all after String-String) instead of
  signaling the §6.2 evaluation error. `isCriteriaTrue()` converts empty to
  false, so `all()`/`exists()`/`where()`/`select()`/`iif` criteria silently
  produced wrong Booleans/collections on the native DuckDB surface.
- **Spec**: N1 §6.2 "the evaluator will throw an error if the types differ";
  §5.1.3 "Otherwise, the result is false" covers criteria evaluating to
  false/empty, NOT evaluation errors.
- **Fix**: new `fhirpathTypeNameForCompareError()` + `throwIncompatibleComparison()`
  helpers before `evalBinaryOp`; both terminal sites now throw
  `FHIRPathSpecError("Type of \"X\" (T) did not match type of \"Y\" (T). InequalityExpression")`
  mirroring the Python core message that
  `udf.py::_is_valid_empty_result_error` accepts. Spec-mandated empty
  comparison results (partial temporal precision `cmp == INT_MIN`,
  calendar-vs-UCUM durations, offset temperatures, incompatible quantity
  base dimensions) are untouched. `FhirpathIsValidFunction`
  (fhirpath_extension.cpp) accepts the new `"Type of " ... "InequalityExpression"`
  prefix so is_valid stays True for execution type errors.
- **Rebuild**: `make fhirpath_extension && make fhirpath_loadable_extension`
  in `extensions/fhirpath/build/release`; artifact redeployed to
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` and the
  user site-packages copy. CQL extension NOT rebuilt (untouched).
- **Regression test**:
  `test_criteria_comparison_type_error_parity_fp03_skeptic` in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py`
  (12 empty-result cases incl. the §5.1 iteration family, 5 spec-mandated
  empties, 3 healthy-value controls, is_valid assertions).

## QA-002 — fallback time-string ordering coercion (MEDIUM)
- **Root cause**: `fhir4ds/fhirpath/engine/invocations/equality.py` `_compare`
  typecheck coerced time-shaped plain strings against `FP_Time` peers for
  ordering (`'10:00' < @T10:30` → true) while native signaled the §6.2 type
  error (empty); contradicted the pinned Time-vs-String equality convention
  (String→Time Explicit-only per §5.5, FP-01 QA-003).
- **Fix**: removed `FP_Time` from both str-vs-temporal coercion conditions
  and from the `FP_Date or FP_DateTime or FP_Time` conversion chains. Time-
  shaped strings vs `@T...`/Date/DateTime peers now raise InequalityExpression
  → wrapper empty → parity. Date/DateTime-shaped string ordering coercion
  (shared convention in BOTH engines) preserved and covered by value controls.
- **Regression test**: `test_time_string_ordering_not_coerced_parity_fp03_skeptic`
  (same file; 5 empty cases, 4 value controls).

## Validation (Recovery Gate)
- Reproducers: `probe.py` 116/116 parity (was 1 fail), `probe2.py` 25/25
  parity (was 8 fails); time-string corner battery 9/9 parity.
- Focused: `pytest fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py`
  → 16 passed.
- Unit/integration: `pytest fhir4ds/fhirpath/` → **1722 passed**.
- Conformance: **2832/2832** (ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47) — baseline held.

## Files changed
- `extensions/fhirpath/src/fhirpath/evaluator.cpp` (helpers + 2 throw sites)
- `extensions/fhirpath/src/fhirpath_extension.cpp` (is_valid classifier)
- `fhir4ds/fhirpath/engine/invocations/equality.py` (typecheck coercion)
- `fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py`
  (2 regression tests)
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
  (+ site-packages copy) — rebuilt binary

## New issues discovered during fix
None. No RETRY_QA flags raised.
