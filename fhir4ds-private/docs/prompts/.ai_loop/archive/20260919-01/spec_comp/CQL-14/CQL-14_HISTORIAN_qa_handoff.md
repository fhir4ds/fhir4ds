# QA Handoff — CQL-14 (Date/Time Operators Part 2), iteration 1, HISTORIAN

## Scope
Re-verified all three SKEPTIC fixes regression-free and hunted new divergences
across §8.9–8.18, dual-engine (Python fallback + native C++), ~90 new probe
cases: `.temp/qa/cql14_historian/probe{1..5}.py` + inline SQL inspection.
Spec verified against live 2019May spec HTML (09-b §8.16/8.17/8.18; interval
§9.24/9.25/9.26 quoted verbatim).

## SKEPTIC fix re-verification (all pass, both engines)
- Bare `same as` (no precision): points AND intervals, spec examples OK.
- Now(): 3-digit millisecond, offset-normalized (`2026-08-21T16:31:05.703-05:00`);
  `Now() = Now()` true; Today() Date-only; TimeOfDay() second-precision `T16:31:05`.
- Mixed Time/DateTime operands: null on same-family AND after/before/on-or family
  (guard covers all comparison paths).

## Issues opened
- QA-001 HIGH: no-precision `same or after` / `same or before` on interval (or
  point-vs-interval) operands is WRONG on native (start-vs-start via
  ExtractTemporalOperand low-of-both) and null on Python. Spec §9.25/§9.26
  require start(left) vs end(right) / end(left) vs start(right), comparing at
  finest precision of either input. Precision variants are correct (translator
  extracts bounds there); the no-precision branch in
  `_translate_same_operator` passes raw interval strings to cqlSameOrAfter/
  cqlSameOrBefore. Diverging repro:
  `Interval[@2012-01-01, @2012-01-02] same or after Interval[@2012-01-01, @2012-01-03]`
  → cpp true / py null / spec false.
- QA-002 LOW: `Time(null)` (single null literal arg) raises ValueError at
  translation — crash instead of null; inconsistent with Time(null,null) → null,
  Date(null) → null, DateTime(null) → null. Spec §8.16 requires ≥1 specified
  component; house convention (spec TimeInvalid example) evaluates to null.

## Verified conformant (new NOT A BUG entries)
- Interval `same <prec> as` compares start AND end per §9.24; point-vs-interval
  treated as singleton interval (end mismatch → false) — correct.
- Date-vs-DateTime same-family comparisons work (implicit conversion);
  no-precision mixed-precision pairs correctly uncertain → null.
- Time ctor: trailing nulls stripped (Time(12,null) → T12), null-gap and
  out-of-range → null; Time(12,30,0,0)=T12:30:00.000, Time(23,59,59,999) OK.
- Subtract: calendar truncation (Mar 31 − 1 mo → Feb 29/28), tz preservation,
  UCUM units (60 'h', 'ms'), Time wraps modulo midnight, week arithmetic,
  null propagation, fractional quantities truncated per Add doctrine.
- `on or after/before day of` point/interval/int-interval matrix correct on
  both engines; no-precision interval before/after via intervalBefore/
  intervalAfter correct; week precision → null (spec note); tz hour-or-finer
  normalization only.

## Baseline
No source changes made by QA. Probes only.
