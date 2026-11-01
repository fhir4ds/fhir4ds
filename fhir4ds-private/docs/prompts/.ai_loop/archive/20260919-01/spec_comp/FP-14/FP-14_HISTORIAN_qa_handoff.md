# QA Handoff — FP-14 (FHIRPath §6.2 Ordering: < <= > >=), HISTORIAN, iteration 1

## Method
Spec verified against the local FHIRPath master spec adoc (§6.2 Comparison,
§6.1 equals timezone discussion, implicit-conversion table). Probes:
`.temp/qa/fp14_historian_2026_08_18/probe.py` — dual-path (native extension
vs forced Python fallback) plus exported-helper probes, focusing on areas the
SKEPTIC pass did not cover.

## SKEPTIC-fix re-verification (all hold, regression-free)
Helper precision-mismatch → None, tz instant ordering, Z=+00:00 equals,
`.0` fractional parse — all correct.

## Verified clean (both engines, zero parity diffs)
- Multi-item operands: `(1|2) < 2`, `Patient.name < 'x'` → empty (spec: error→empty).
- Type-mismatch operands: `5 < '5'`, `true < 1`, `@T12:00:00 < @2014-01-01`,
  `5 < 4 'm'` → empty.
- Spec timezone-conversion examples: `@2017-11-05T01:30:00.0-04:00 < @2017-11-05T01:15:00.0-05:00` → true (all four ops correct).
- One-sided timezone offsets: parity OK, definitive compare at raw values (spec: implementation decision).
- Time-valued quantities: `1 year > 1 'a'` empty, `10 seconds > 1 's'` true,
  `1 'min' > 61 's'` false (matches spec examples + FP-01 doctrine).
- Chained ordering `1 < 2 < 3` → empty. Resource-driven `birthDate` cases.

## Issues filed
- QA-001 (HIGH, CONFIRMED): native `compareDateTimes` truncates fractional
  seconds to 3 digits; Python fallback compares full decimal precision →
  PARITY DIVERGENCE and §6.2 "decimal comparison semantics" violation.
  `@...00.1234 < @...00.1236`: native false vs python true; equality native
  true vs python false; same for @T times. Root cause:
  `extensions/fhirpath/src/fhirpath/evaluator.cpp` `parseDateTimeParts`/
  `parseTimeParts` (`ms_str.substr(0,3)`) — needs full-precision fraction
  retention in `DateTimeParts` + decimal fraction compare; requires extension
  rebuild + redeploy.
- QA-002 (MEDIUM, CONFIRMED): exported helper `DateTimeComparisons` Time-vs-
  Date/DateTime ordering returns definitive booleans; engine returns empty
  (no Time↔Date/DateTime implicit conversion exists). 10th instance of the
  exported-helper-API-forgotten family.
- QA-003 (MEDIUM, CONFIRMED): helper `_engine_compare` crashes with
  AttributeError when an FP temporal constructor returns None (e.g.
  `FHIRDate.from_string('2018-03-01+05:00')` is over-accepted; dates carry no
  offset). Public API must return None (empty), not crash.
- QA-004 (LOW, UNCONFIRMED/DEFERRED): Date-vs-DateTime ordering is definitive
  at shared coarser precision (`@2018-03-02 > @2018-03-01T12:00` → true in
  both engines). Spec prose is self-conflicting; no official fixture covers
  it; both engines agree. Deferred to human/spec clarification — do not
  spec-game a change without an anchor.

## Fix direction (for Remediation)
- QA-001: add `frac_digits` (full fractional string) to `DateTimeParts` in
  evaluator.cpp; in `compareDateTimes`, when both operands are second-level
  precision and seconds are equal, compare fractions as decimals
  (right-pad to equal width, lexicographic). Keep truncated `millisecond`
  for other uses. Rebuild + redeploy extension (repo bundle AND user
  site-packages). Add native-vs-fallback parity test.
- QA-002/QA-003: Python-only guards in `_engine_compare` — return None when
  FP node construction yields None, and when operand helper types are not
  both Date/DateTime (Time never compares to Date/DateTime).
