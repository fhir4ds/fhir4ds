# QA Handoff — CQL-14 (Date/Time Operators Part 2), iteration 1, SKEPTIC

## Scope tested
CQL 1.5 §8.9–8.18 (verified against live 2019May spec HTML + official Cql.g4 +
official cql-tests XML): Now(), Today(), TimeOfDay(), Same As / Same Or After /
Same Or Before [precision], On Or After / On Or Before [precision] (+ `after or
on` / `before or on` variants), Subtract (DateTime/Date/Time − Quantity),
Time() constructor, and partial-precision (birthDate-style) comparison patterns.
Dual-engine (Python fallback + native C++ extension) on every case.

Probes: `/mnt/d/fhir4ds/.temp/qa/cql14_skeptic/probe{1..4}.py` (~120 cases).

## Issues opened
- QA-001 MEDIUM: bare `same as` (no precision) rejected by parser (points AND
  intervals); grammar `concurrentWithIntervalOperatorPhrase` allows it; spec
  defines no-precision semantics. `same or after/before` no-precision parse —
  asymmetry confirms gap. Translator already has a dormant `"same as"` branch.
- QA-002 LOW: mixed Time vs DateTime operands to same-family comparisons give
  definitive `false` instead of null (cross-type pair undefined in signatures).
- QA-003 LOW: Now() emits microsecond precision; CQL DateTime model stops at
  millisecond.

## Verified conformant (NOT A BUG registry additions)
- Uncertainty semantics match every spec example: same as → null when either
  operand coarser than requested precision; same or after/before → definitive
  true/false when ordering provable at a coarser component, null when uncertain.
- Timezone normalization at hour-or-finer only: matches Java reference engine
  `DateTime.getNormalized` (precision > DAY → evaluation-zone normalize). Day
  precision compares raw components — `same day` across ±offsets NOT normalized.
- Subtract mirrors CQL-13 Add: calendar truncation (Mar 31 − 1 mo → Feb 28/29),
  tz offset preservation, unit allowlists (Date − hours → null; Time − day →
  null), convert-and-truncate (DateTime(2014) − 18 months → 2013T).
- Time() ctor: trailing nulls stripped, null-above-specified rejected, all
  out-of-range components → null.
- Today() is Date-only; Now()=Now() deterministic within a library; both carry
  local evaluation-request offset; TimeOfDay() second-precision Time.
- `(-1) day` (paren-neg quantity) parse rejection matches Cql.g4 (`quantity:
  NUMBER unit?`); `- -1 day` works.
- `'2012T'` rendering of DateTime(2014) is the internal DateTime marker
  convention (distinguishes DateTime from Date), consistent everywhere.

## Baseline
No source changes were made by QA. Conformance gate untouched this phase.
