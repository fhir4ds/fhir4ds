# QA Handoff — FP-14 (FHIRPath §6.2 Ordering: < <= > >=), SKEPTIC, iteration 1

## Probes (all dual-path: native extension vs forced Python fallback, PYTHONPATH=/mnt/d/fhir4ds)
- `.temp/qa/fp14_skeptic_2026_08_18/probe.py` — 64 adversarial cases: fixture
  anchors, string code-point ordering (Z<a, prefix, empty string, emoji
  U+1F600 > U+FFFD — code-point semantics confirmed), temporal
  precision/timezone/instant semantics (Z=+00:00, offset equal instants,
  cross-precision empty, Date-vs-DateTime empty), Boolean operands error→empty,
  Integer/Decimal exactness at 28 significant digits, quantity ordering
  (strict, no tolerance; derived units; calendar factors; mm[Hg]/Pa;
  incompatible dims and offset temps empty), empty propagation both positions,
  iteration-criteria chaining (where/all/select/iif). ZERO parity diffs,
  ZERO spec violations in the ENGINE paths.
- `.temp/qa/fp14_skeptic_2026_08_18/fixtures.py` — full official R4 fixture
  batch for testLessThan/testLessOrEqual/testGreaterThan/testGreaterOrEqual
  (81 tests incl. resource-driven `Observation.value < 200 '[lb_av]'`):
  81/81 correct in BOTH engines.
- Helper probe (inline): exported `DateTimeComparisons` in
  `fhir4ds/fhirpath/duckdb/functions/datetime.py` deviates (issues below).

## Issues filed
- QA-001 (MEDIUM, OPEN): helper returns booleans for precision-mismatched
  temporal ordering; spec/fixtures require empty. (9th "exported helper API
  forgotten" instance.)
- QA-002 (MEDIUM, OPEN): helper DateTime ordering ignores timezone offsets
  (naive local compare); `equals` Z vs +00:00 False (spec True).
- QA-003 (LOW, OPEN): helper `DateTimeLiteral.parse_datetime/parse_time`
  reject 1–2 digit fractional seconds (`.0`) that engines and fixtures use.

## Doctrine re-verifications (all held)
FP-01 calendar factors (1 month > 29 'd' true / > 30 'd' false), FP-02
derived units + mm[Hg]/Pa ordering, FP-03 throwIncompatibleComparison inside
criteria ((1|'a'|3).all($this > 0) → empty in both), Boolean ordering
error→empty in both engines, 29-digit Integer literals empty (FP-06).

## Fix direction (for Remediation)
Python-only exported-helper module; engines are correct. Delegate
DateTimeComparisons comparisons to the engine's canonical FP_DateTime/
FP_Date/FP_Time compare() (rendering the helper value back to its lexical
form) per the FP-09/FP-11 delegate-to-engine doctrine; no extension rebuild.
