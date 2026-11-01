# Engineer Handoff — CQL-10 EXPLORER FIX, iteration 1 (2026-08-21)

Both QA issues resolved at root cause, dual-engine, with focused regression
tests. Full conformance recovery gate: **2832/2832** (ViewDefinition 144/144,
FHIRPath 935/935, CQL 1706/1706, DQM 47/47) — baseline holds.

## QA-001 (HIGH) — RESOLVED

`1000 'mg' / 1 'g'` returned `1000 'mg/g'` (wrong value AND unit) on both
backends. Reference engine (cqframework `DivideEvaluator.kt`, main) applies
`ucumService.divideBy`, which converts and cancels commensurable units →
`1.0 '1'`. Spec: CQL 1.5 §9.4 "the resulting quantity will have the
appropriate unit".

Fixes (dual-engine lockstep):
- `fhir4ds/cql/duckdb/udf/quantity.py` `quantityDivide`: apply pint
  `to_reduced_units()` after division. Commensurable units cancel to `1`
  with the conversion factor applied; incommensurable compounds (`mg/mL`)
  and exponent reductions (`cm2/cm` → `cm`) unchanged; div-by-zero still
  null.
- `extensions/cql/src/cql/quantity.cpp` `quantity_divide`: new
  `units_compatible(code1, code2)` branch converts both magnitudes via
  `to_base` and divides, emitting unit `1` (mirrors reference semantics).
- Extension rebuilt and deployed: md5 `2722c674ccbdd1e542e4949f8f65c6ae`
  verified identical across repo bundle
  (`fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`) and site-packages;
  `~/.duckdb/extensions/` cache had no stale cql binary. Fix re-verified
  through fresh reloaded cpp connections in the parity test.

## QA-002 (MEDIUM) — RESOLVED

Statically-known scalar-vs-Quantity mixtures (`1 + 1 'mg'`, `1 'mg' - 1`,
`10 / 2 'mg'`, `2 ^ 2 'mg'`) and Quantity inputs to
Ceiling/Floor/Exp/Ln/Log/High/LowBoundary silently translated to NULL.
Reference raises InvalidOperatorArgument; the CQL-10 HISTORIAN typed-guard
contract required a typed TranslationError.

Fixes (translator only, no runtime change):
- `fhir4ds/cql/translator/expressions/_functions.py`: new
  `_ARITHMETIC_FN_QUANTITY_REJECTED` set;
  `_validate_static_arithmetic_operands` rejects statically-known Quantity
  operands for Ceiling/Floor/Exp/Ln/Log/High/LowBoundary (Abs keeps its
  valid CQL §16 Quantity overload). Null/Any/dynamic operands still pass
  through to runtime null semantics.
- `fhir4ds/cql/translator/expressions/_operators.py`: new binary guard —
  `+`/`-` reject any statically-known scalar-numeric/Quantity mixture,
  `/` rejects scalar-left+Quantity-right, `^` rejects any Quantity operand.
  Deliberately NOT rejected (valid per §9 / fixtures): `Quantity / Decimal`
  (fixture Divide1Q1Q), `*` in either scalar/Quantity order, temporal
  +/- Quantity, and all Quantity/Quantity arithmetic.

## Tests

- `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py`:
  new `test_cql10_explorer_quantity_divide_unit_cancellation_and_typed_mixed_guards`
  (8 quantity-division/unit cases asserted identical on python+cpp engines,
  15 typed-TranslationError cases, temporal+quantity and Q/scalar still
  valid). File now 10/10 pass.
- Updated `test_cql_dynamic_fhir_arithmetic_edges_match_cpp_and_python`:
  `10 'mg' + 2`, `2 + 10 'mg'`, and `(O.value as Quantity) + 1` moved from
  silent-null expectations to pytest.raises(TranslationError) — intentional
  doctrine tightening, not a regression.

## Validation

- Arithmetic parity files: 10/10 + part2 10/10 (run together: 19/20 pre
  expectation-update, 10/10 after; final state all green).
- Full conformance `conformance/scripts/run_all.py`: 2832/2832.
- Full `pytest fhir4ds/cql` unit+integration sweep: **5740 passed, 9 env
  skips, 0 failures** (1140s).

No new issues discovered during remediation.
