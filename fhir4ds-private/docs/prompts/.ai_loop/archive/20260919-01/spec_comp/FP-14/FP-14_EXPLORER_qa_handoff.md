# FP-14 EXPLORER QA Handoff (2026-08-18)

Personality: EXPLORER (3rd personality on FP-14 §6.2 Comparison > < <= >=).
An earlier interrupted attempt created `.temp/qa/fp14_explorer_2026_08_18/`;
its harness had a string-vs-list comparison bug (most "SPEC-DIFF"s were
artifacts) but surfaced 3 genuine native-vs-fallback parity diffs. This rerun
(`.temp/qa/fp14_explorer2_2026_08_18/probe.py`, 23 focused dual-path cases plus
the interrupted probe's 82-case battery + 20 is_valid checks) confirmed all
three; everything else (boolean/iif chaining, conversions feeding <, int64
bounds, 28-digit decimals, tz offsets crossing date boundaries, quantity
tolerances/magnitude ratios, Unicode code-point string ordering, where/repeat
heterogeneous collections, comparison-into-arithmetic, is_valid parity) is
CLEAN — native and fallback agree and match spec/fixture doctrine.

## Issues filed (all Python-fallback-only; native engine is spec-correct)

- **QA-001 (HIGH, CONFIRMED)**: fallback DateTime ordering/equality truncates
  fractional seconds at microseconds. `@2018-03-01T10:30:00.1234567 <
  @2018-03-01T10:30:00.1234568` → false (native true; §6.2 decimal fraction
  semantics). Root cause: `FP_TimeBase.compare`/`equals` equal-precision
  branch compares `_getDateTimeInt()` from a dateutil `timestamp()`.
- **QA-002 (HIGH, CONFIRMED)**: fallback FP_Time literals with 7–9 fractional
  digits fail strptime `%f` (6-digit cap) → `_pyTimeObject` None → all
  ordering (incl. `.999999999 < next second`) errors → empty. Native correct.
- **QA-003 (MEDIUM, CONFIRMED)**: fallback equal-precision Date-vs-DateTime
  ordering compares incommensurate scales (FP_Date multiplier-sum ~6.4e10 vs
  FP_DateTime epoch timestamp ~1.45e9): `@2015-01-01 <
  '2016-01-01'.toDateTime()` → false (native true; literal-vs-literal
  equivalent is true). Operand-order dependent.

Doctrine pins reconfirmed: probe-harness outputs are lists of strings
(`['true']`); `+14:00` vs `-12:00` "same instant" probe comments must use
correct UTC arithmetic (00:00+14:00 == 2019-12-31T10:00Z ≠ 12:00-12:00).

No extension rebuild needed — native path already correct (FP-14 HISTORIAN
frac_digits fix). All fixes land in `fhir4ds/fhirpath/engine/nodes.py`.
