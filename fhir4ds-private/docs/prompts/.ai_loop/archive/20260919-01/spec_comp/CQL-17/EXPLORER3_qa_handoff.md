# QA Handoff — CQL-13 (EXPLORER), iteration 1

Chunk: CQL 1.5 Date/Time Operators Part 1. Personality: EXPLORER.
Spec verified live: CQL 1.5 STU4 (cql.hl7.org/2019May 09-b-cqlreference.html),
constructor + duration sections fetched this session; prior launches' §8.1–8.8
verification inherited.

Method: 90+ dual-engine probes (translate_cql + DuckDB execution on native
cpp and python-supplement-only connections) plus end-to-end population-sql
runs with retrieved FHIR fields (partial birthDates, deceasedDateTime).
Probes: .temp/qa/cql13_expl/{probe4,probe5,probe6,probe7}.py.

Verified conformant (py==cpp, spec-checked): calendar-boundary negative Add
(Jan 31 - 1 month -> Dec 31; Mar 31 - 1 month -> Feb 28/29 incl. dynamic;
leap Feb 29 - 1 year -> Feb 28), tz-offset preservation in Add, DateTime
constructor with tz args (incl. fractional +05:30), Component From
timezoneoffset (Z -> 0.0, Date -> null), mixed-precision After/Before with
explicit precision (truncation vs uncertainty -> null), month/leap-year
durations, Difference vs Duration sign symmetry (-2/-2), sub-day boundary
counting across midnight and tz-offset pairs, mixed aware/naive -> null,
Sunday week-difference re-check, uncertainty intervals for month/day
mixed-precision operands ([1,2] months, [34,64] days, [23,47] hours),
partial-FHIR-date retrieval through aliases and boolean exprs (p2 nulls
propagate correctly), out-of-range static constructor args -> translation
error.

Issues (see evolution.json):
- QA-001 (HIGH): years-duration (and AgeInYears) with month-precision
  operand returns crisp max instead of uncertainty interval; partial
  birthDate '1975-03' + AgeInYearsAt(@2020-03-01) -> 45 (could be 44).
  Both engines. Inconsistent with the repo's own interval convention
  (official test years between DateTime(2005) and DateTime(2010) ->
  Interval[4,5]).
- QA-002 (HIGH): py engine returns null for years-between with tz-aware
  DateTime second operand; cpp returns 44. Dual-engine lockstep violation.
- QA-003 (MEDIUM): DateTime constructor with trailing null components AND
  timezoneoffset arg -> null (spec sanctions trailing nulls); Date(2024,
  null) -> null though DateTime(2024,1,1,null) truncates.

NOT A BUG registry: '(-1) month' parenthesized negative quantity ->
ParseError is grammar-correct ('-1 month' and '+ -1 month' work); DateTime
tz=null -> naive local datetime (spec defaults unspecified tz to evaluation
request tz); years between @2020-02-29 and @2021-02-28 = 1 (truncation
add convention @2020-02-29 + 1 year = @2021-02-28 makes it consistent);
difference in years on month-precision operands is crisp (boundary
crossings deterministic) — only DURATION needs the interval.
