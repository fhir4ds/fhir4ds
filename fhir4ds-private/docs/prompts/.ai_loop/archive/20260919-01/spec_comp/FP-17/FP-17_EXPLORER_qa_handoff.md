# QA Handoff — FP-17 iteration 1 (EXPLORER)

Chunk: FHIRPath §6.5 Boolean Logic (and, or, not(), xor, implies).
Personality: EXPLORER — boundary probing of toBoolean-convertible operands.

## Probed
- Truth tables with true/false/{} via literals and resource fields (regression re-check — clean).
- Empty operands from where()/exists() projections, iif-produced operands, nested trees mixing all
  five operators, precedence, chained implies — all clean (matches prior SKEPTIC/HISTORIAN results).
- toBoolean-converted operands in boolean logic: 0, 1, 0.0, 1.0, 'true', 'false', '1', '0' as
  operands of and/or/xor/implies and input to not(), across all three engines
  (core Python engine via `fhir4ds.fhirpath.evaluate`, DuckDB native C++ extension, forced Python
  fallback). Native/fallback parity holds everywhere.
- Probes: `.temp/qa/fp17_explorer/probe_core.py`, `.temp/qa/fp17_explorer/probe_db.py`.

## Finding: QA-001 (HIGH, OPEN)
Boolean-logic singleton Boolean evaluation skips the toBoolean conversion step required by
§6.5 + Singleton Evaluation of Collections. Convertible operands (0, 0.0, 'false', 'no', 'n', '0')
are treated as truthy `true` instead of their converted value.

Examples (all three engines, identical): `0 and true` → true (spec: false); `0 xor false` → true
(spec: false); `'false' implies false` → false (spec: true); `t implies 'false'` → true (spec:
false); `'false'.not()` → false (spec: true); `0.not()` → false (spec: true).

Root-cause sites:
- `fhir4ds/fhirpath/engine/invocations/logic.py::_singleton_boolean` (non-bool item → True)
- `fhir4ds/fhirpath/engine/invocations/existence.py::not_fn` via `misc.boolean_singleton`
- `fhir4ds/fhirpath/duckdb/operators.py::_get_boolean_value` (returns True) + `boolean_not`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp::collectionIsBool` ("Any other singleton value is truthy")

Non-convertible singletons ('x', 5 → true) are already correct and MUST be preserved (second
branch of Singleton Evaluation). `not(0)` (function-invocation-with-arg arity error) is intended
behavior per prior HISTORIAN launch; the dot form `X.not()` is the affected surface.

## Verified against
FHIRPath R4 spec §6.5 (cached normative asciidoc at
`.temp/qa/fp01_historian_2026_08_16/fhirpath_master_spec.adoc` lines 474-499 and 2108-2187).
