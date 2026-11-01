# Engineer Handoff — FP-11 §5.7 Math (HISTORIAN), iteration 1

## QA-001 (MEDIUM, SPEC_VIOLATION) — RESOLVED

Root cause: the FP-11 SKEPTIC engine fixes (invocations/math.py `power()`,
`rround()` + native evaluator.cpp) were never propagated to the exported
direct-helper module `fhir4ds/fhirpath/duckdb/functions/math.py`.

Fix (Python-only; no extension rebuild needed — native path already correct):
- `power()`: now mirrors engine §5.7 semantics — Integer base + Integer
  exponent → Integer result within int64 (beyond: exact Decimal digits);
  negative Integer exponent on Integer base → empty; `0^<=0` and
  negative-base-non-integral-exponent → empty; integral Decimal exponents
  computed exactly via Decimal (no binary64 noise, normalize + ".0" shaping);
  non-integral exponents → binary64 shortest-round-trip (shared doctrine).
- `round_fn()`: zero results `copy_abs()`ed (no `-0.0`).

Regression coverage: `TestFp11HistorianMathHelperEngineContract` (5 tests) in
`fhir4ds/fhirpath/duckdb/tests/unit/test_math.py`.

## QA-002 (LOW) — INTENDED, no change

Transcendental <=1 ULP drift between std::pow (extension) and libm
(math.pow, fallback) re-pinned per FP-11 SKEPTIC QA-006 doctrine.

## Validation

- Unit math tests: 109 passed.
- Integration `test_math_parity.py`: 12 passed.
- Full conformance: **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held.
