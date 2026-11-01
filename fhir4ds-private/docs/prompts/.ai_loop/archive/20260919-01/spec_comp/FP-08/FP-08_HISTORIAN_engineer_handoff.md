# Engineer Handoff — FP-08 HISTORIAN (iteration 1, 2026-08-17)

## Triage
- QA-001 PARITY (MEDIUM, CONFIRMED): reproduced in
  .temp/qa/fp08_historian_2026_08_17/probe2.py (4 dual-path diffs).
- QA-002 SPEC_VIOLATION (MEDIUM, CONFIRMED): direct helper
  to_quantity("1 'year'", "day") -> None vs engine 365 day.

## Fixes (both Python-side; native already exhibited desired behavior —
no extension rebuild required)
1. QA-001: new `FP_Quantity._divide_and_render(numerator, denominator)`
   in `fhir4ds/fhirpath/engine/nodes.py` — decides exactness with
   `Fraction` on the PRE-division numerator/denominator (an after-the-fact
   check on the Decimal result is wrong: every finite Decimal looks
   terminating, which initially stripped the FP-08 SKEPTIC-pinned
   trailing zero in 1 day -> 0.002739726027397260273972602740 year —
   caught by the existing regression test and corrected). Exact
   terminating quotients trim trailing scale zeros ("1.80" -> "1.8",
   "6.0" -> "6", "1.000" -> "1"); non-terminating quotients keep the
   28-significant-digit ROUND_HALF_EVEN rendering verbatim. Applied at
   the three conversion division sites: conv_duration_to_spec and the
   weeks/days and m/cm branches of conv_unit_to. Comparison/arithmetic
   callers of conv_unit_to are Decimal-scale-insensitive, so their
   semantics are unchanged (verified by the full fhirpath tree).
2. QA-002: `_convert_quantity` in
   `fhir4ds/fhirpath/duckdb/functions/conversion.py` now routes through
   `conv_duration_to_spec` before `conv_unit_to`, matching the engine's
   §5.5.7 duration table (FP-09 direct-helper doctrine).

## Validation (Recovery Gate)
- New regression tests:
  `test_toquantity_terminating_conversion_no_scale_artifacts_fp08_historian`
  and `test_direct_helper_toquantity_duration_table_fp08_historian` in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_spec_quantity_time_parity.py`.
- Full FP-08 parity file: 5/5 pass.
- Both HISTORIAN probes: 117/117 (71 + 46), zero parity diffs.
- `pytest fhir4ds/fhirpath`: 1745 passed.
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, OVERALL 2832/2832 (baseline held).

## Files changed
- fhir4ds/fhirpath/engine/nodes.py (new _divide_and_render; 3 call sites)
- fhir4ds/fhirpath/engine/invocations/misc.py (comment pointer only)
- fhir4ds/fhirpath/duckdb/functions/conversion.py (duration-table routing)
- fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_spec_quantity_time_parity.py
  (2 new tests)

No new issues discovered during remediation. Both issues RESOLVED.
