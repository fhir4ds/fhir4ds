# DESIGN HANDOFF — WASM function-surface parity

## Plan

`fhir4ds-private/docs/architecture/plans/FEATURE_WASM_SURFACE_PARITY.md` (v2)

## Summary

Close the remaining desktop ↔ DuckDB-WASM conversion-function gaps with
**behavioral** parity (value + SQL type) and upgrade the macro-sync contract
from names to behavior.

- Class A (pure SQL macros: `ToString`, `ToInteger`, `ToDecimal`, `ToBoolean`,
  `ConvertsToString`, verify `ConvertsToInteger`): copy the desktop macro SQL
  into `cql-macros.ts`; no C++.
- Class B (Python-UDF-backed: `ToDateTime`, `ToTime`, `ToLong`, `ToRatio`,
  `Convert[s]To*`, `CanConvertQuantity`): port to C++ scalars in
  `extensions/cql/src/cql_extension.cpp`, registered with
  `RegisterSpecialScalar`; remove now-shadowing TS macros; desktop keeps its
  Python authority.
- Class C (list-equality family, `ExpandValueSet`, `CQLListMode`): stay
  allowlisted, documented.
- Test-only harness `fhir4ds/operations/tests/wasm_surface_harness.py` runs the
  browser-equivalent surface (C++ extensions + TS macros extracted verbatim)
  against desktop `register()` over a spec-grounded corpus.

## How the plan was refined

Self-audit (`ARCHITECT_REVIEW.md`) raised 7 notes, all applied in v2:

1. Actionable scope narrowed to the conversion family (allowlisted names are not
   chased).
2. Harness compares `(value, typeof)` — the ToDate defect was a type bug.
3. Class A inventory decisions made per function (copy vs keep vs verify).
4. `ToInterval`/`ToPrevalenceInterval` confirmed library-defined → out of scope.
5. `CanConvertQuantity` confirmed translator-reachable → in scope.
6. Harness executes TS macros verbatim (no hand-copied SQL).
7. Per-function red→green evidence required.

## Evidence base

- S32 ToDate fix (landed): C++ scalar, TS macro removed, native+WASM rebuilt,
  wheel `93eed0b5…`, standalone cms125 cells clean, conformance 2832/2832.
- Three-connection audit: `/tmp/opencode/surface_diff.json`,
  `/tmp/opencode/macro_body_diff.json`.
- Existing contract: `fhir4ds/operations/tests/test_macro_sync.py`
  (name parity + 22-entry allowlist).

## Approval requested

Approve the v2 plan (or amend scope/order). On approval the loop advances to
`feature_implementation`: harness first (red tests), then the C++ ports, then
macro alignment, contract upgrade, artifacts, gates.

## Risks the approval should weigh

- Porting `ConvertsTo*` is ~10 functions; each lands behind its own no-Python
  test so it can stop safely between ports.
- `ExpandValueSet` and the list-equality family remain browser gaps in this
  campaign by design.
- Target version stays 0.0.18 (release not yet committed/published).
