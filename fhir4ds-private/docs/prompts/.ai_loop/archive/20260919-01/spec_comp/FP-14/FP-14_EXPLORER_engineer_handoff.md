# FP-14 EXPLORER Engineer Handoff (2026-08-18)

All 3 QA issues RESOLVED. Fixes are Python-fallback-only in
`fhir4ds/fhirpath/engine/nodes.py` (native engine already spec-correct per the
FP-14 HISTORIAN frac_digits fix — no extension rebuild).

## Fixes

- **QA-001 (HIGH)** — fallback DateTime ordering/equality truncated
  fractional seconds at microseconds. `FP_TimeBase.compare()` and
  `equals()` equal-precision branches now compare normalized components and
  the raw fraction digit strings decimally (new `_fraction_digits()` +
  `_compare_decimal_fractions()` helpers). Missing fraction = "0";
  right-pad to equal width; trailing zeros add no precision (fixtures
  testLessThan26/27).
- **QA-002 (HIGH)** — FP_Time literals with 7–9 fractional digits left
  `_pyTimeObject` None (strptime `%f` 6-digit cap) so ordering errored to
  empty. Added a manual time-object fallback in `FP_Time.__init__`
  (fraction truncated to µs for display/arithmetic only; ordering uses the
  exact digit strings).
- **QA-003 (MEDIUM)** — equal-precision Date-vs-DateTime ordering compared
  FP_Date multiplier-sum ints (~6.4e10) against FP_DateTime epoch
  timestamps (~1.45e9). The `compare()` final branch is now componentwise
  on the tz-normalized lists, removing the scale mix entirely.

## Validation

- Reproducer probe `.temp/qa/fp14_explorer2_2026_08_18/probe.py`:
  0/23 parity diffs (was 13).
- Interrupted 82-case battery: 0 parity diffs (remaining "spec diffs" are
  that harness's known string-vs-list comparison artifacts).
- Regression: `test_comparison_parity.py::
  test_subsecond_and_cross_type_comparison_parity_fp14_explorer`
  (13 dual-path cases); file total 107 passed.
- Full fhirpath pytest tree: 1909 passed.
- Conformance: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) —
  baseline held.

No new issues discovered during remediation.
