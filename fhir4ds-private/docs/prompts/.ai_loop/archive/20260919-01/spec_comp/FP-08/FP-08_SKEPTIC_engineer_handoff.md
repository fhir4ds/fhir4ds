# Engineer Handoff — FP-08 (iteration 1, 2026-08-17)

## Fixes (all issues RESOLVED, dual-engine, extension rebuilt + redeployed)

### QA-003 (HIGH) — fallback T-prefixed partial Time equality
- Root cause: `FP_Time.__init__` strptime format list (engine/nodes.py)
  lacked non-timezone `"T%H:%M"`, `"T%H"`, and bare `"%H"` forms; partial
  T-times got no `_pyTimeObject`, so `FP_TimeBase.equals()` compared
  `_getDateTimeInt()` None vs int.
- Fix: added the three formats. `'T14:34'.toTime() = @T14:34` now true,
  matching native.

### QA-001 (MEDIUM) — §5.5.7 calendar conversion table not honored
- Root cause: June FP-08 group separation (year/month vs day-and-below)
  enforced in `conv_unit_to` (equality-oriented) also gated the
  toQuantity path in both engines, blocking the spec's direct rows
  (1 year = 365 days, 1 month = 30 days).
- Fix: new toQuantity-only conversion `FP_Quantity.conv_duration_to_spec`
  (engine/nodes.py) routing duration pairs through exact rationals with
  the direct table factors; used by `to_quantity` before `conv_unit_to`.
  Native: `durationSpecMagnitude` + `exactDecimalRatioText` branch in
  `convertQuantityUnit` (evaluator.cpp) before the group guard.
  Calendar↔UCUM cross-category rejection (1 year -> 's' empty) preserved,
  pinned by test_calendar_vs_ucum_duration_group_separation_fp08_explorer.

### QA-002 (MEDIUM) — Decimal precision parity (15 vs 28 sig digits)
- Root cause: native conversion computed in binary64 with a 15-sig-fig
  shortest-round-trip render cap; Python Decimal context = 28 sig digits.
- Fix: native `exactDecimalRatioText` performs exact __int128 long
  division and renders 28 significant digits ROUND_HALF_EVEN (§4.1.4),
  applied to all duration-unit conversions; `quantity_value` is the
  strtod of the rendered text so `.value` and toString agree.
  Example now: (1 's').toQuantity('min') → "0.01666666666666666666666666667 'min'"
  in BOTH engines.

## Incidental (logged, fixed)
- Stale unit expectations `test_plus_days_preserves_timezone_z`
  (both copies) still expected the pre-FP-07 `+00:00` normalization;
  updated to the pinned Z-preservation doctrine (Z kept verbatim).

## Validation
- New regression: fhir4ds/fhirpath/duckdb/tests/integration/
  test_fp08_spec_quantity_time_parity.py (3 tests, dual-path) — PASS.
- pytest fhir4ds/fhirpath/duckdb/tests — 1564 passed, 0 failed.
- pytest fhir4ds/fhirpath/tests — 178 passed, 0 failed.
- Conformance master gate: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 — OVERALL 2832/2832 (baseline held).
- Probe rerun (.temp/qa/test_fp08_skeptic.py + round2): 137 cases,
  0 parity diffs, 0 real spec mismatches.
- Extension rebuilt (make fhirpath_loadable_extension) and copied to
  repo bundle fhir4ds/fhirpath/duckdb/extensions/, user site-packages,
  and ~/.duckdb extension caches.

## Files changed
- fhir4ds/fhirpath/engine/nodes.py (FP_Time formats; duration spec table)
- fhir4ds/fhirpath/engine/invocations/misc.py (to_quantity routing)
- extensions/fhirpath/src/fhirpath/evaluator.cpp (native duration path)
- extensions build artifacts: fhirpath.duckdb_extension (bundle + caches)
- tests: test_fp08_spec_quantity_time_parity.py (new);
  test_fhirpathpy_datetime.py x2 (stale Z expectation)
