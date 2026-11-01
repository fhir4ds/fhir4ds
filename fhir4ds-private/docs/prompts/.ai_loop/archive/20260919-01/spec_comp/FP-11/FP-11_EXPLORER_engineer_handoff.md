# Engineer Handoff — FP-11 evolution iteration 1 (FIX), 2026-08-17

## Situation on resume
The previous session was interrupted after QA but the native fixes for both
issues had already been applied to `extensions/fhirpath/src/fhirpath/evaluator.cpp`
(marked `FP-11 EXPLORER QA-001/QA-002 (2026-08-17)` comment blocks) and the
extension rebuilt + redeployed (repo bundle `fhir4ds/fhirpath/duckdb/extensions/`,
user site-packages, `~/.duckdb/extensions/v1.5.2` — all timestamps 13:05).
State files were stale ("no fixes attempted"). This session verified the fixes
at root cause, added the missing focused regression tests, and validated.

## QA-001 (HIGH, RESOLVED) — formatDecimalNumber truncation
- Root cause: native `formatDecimalNumber` rendered non-subnormal scientific
  doubles via `std::fixed << setprecision(15)`, eating significant digits
  behind leading fractional zeros (1e-27.sqrt() -> '0.000000000000032', ~1%
  error; 1e-28.sqrt() -> '0.0') and rendering large values as the exact
  binary64 expansion.
- Fix: non-subnormal scientific values expand `shortestRoundTripText(value)`
  via `expandScientificToFixed` — the canonical `format(Decimal(str(float)),
  "f")` fallback rendering. Subnormal <1e-300 keeps scientific form (doctrine).
- Verified: probe/probe2/probe3 all zero divergence;
  `test_math_parity.py::test_transcendental_tiny_decimal_rendering_parity_fp11_explorer2`.

## QA-002 (MEDIUM, RESOLVED) — powerDecimalExactText bail-outs
- Root cause: scale>20 / >10000-magnitude-digit / negative-exp total_scale>100
  guards silently degraded to `std::pow` while the fallback computes exact
  Decimal 28-sig (1.0000001.power(1000000) wrong at 11th sig digit; 1e-27
  .power(2) -> '0.0').
- Fix (all in evaluator.cpp, FP-11 EXPLORER QA-002 block): scale>20 guard
  dropped; oversized magnitudes route Decimal bases to
  `powerDecimalGuarded28Text` (log-time binary exponentiation) instead of
  std::pow; integer base + positive exponent keeps the documented exact-digit
  degrade; negative-exp cap raised to 10000 with guarded-28 fallback;
  fractional long-division digits raised to 10100 (2.0.power(-1023) retains
  28 sig digits); `1^e` short-circuit (anti-DoS); subnormal-scale results
  render shortest-round-trip scientific ((0.5).power(1074) -> '5e-324').
- Verified: same probes +
  `test_math_parity.py::test_power_exact_decimal_no_bailout_parity_fp11_explorer2`.

## Validation
- New regression tests: 2 tests appended to
  `fhir4ds/fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py`
  (file: 14/14 passed).
- Conformance blocker gate: `conformance/scripts/run_all.py` —
  ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  OVERALL 2832/2832 (baseline held).
- Reproducers `/mnt/d/fhir4ds/.temp/qa/fp11_explorer/probe{,2,3}.py`: zero
  native-vs-fallback divergences.

## New issues discovered
None.
