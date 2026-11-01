# QA Handoff — CQL-14 (Date/Time Operators Part 2), iteration 1, EXPLORER

## Scope
Boundary/combination probing per chunk mandate: qualifier (starts/ends/occurs) ×
comparison-family × precision matrices, open/closed unbounded bounds, Time-only
intervals, mixed-precision point-vs-interval uncertainty, Now()/Today()/
TimeOfDay() in arithmetic + comparisons, Subtract with timezone-carrying
operands and sub-second quantities, Time() ctor fractional/near-boundary
components, boolean chains + define aliases, and full e2e DuckDB execution over
retrieved FHIR data — all dual-engine (native C++ vs Python supplements).
Workspace: `.temp/qa/cql14_explorer2/` (harness.py + probe1..5).

## Issues opened (2)
- QA-001 HIGH: `starts/ends same <prec> or after|or before` mis-parses — the
  parser drops the `or after`/`or before` qualifier (consumes `or` as if it
  were `as`), lowering to `same as` equality → definitive wrong booleans
  (e.g. `Interval[@2012-01-02, @2012-01-05] starts same day or after
  @2012-01-01` → false; spec: true). No-precision `starts same or after` →
  ParseError. Spec: §9.18/§9.19 "same is a synonym for on"; reference
  cql-to-elm visitConcurrentWithIntervalOperatorPhrase produces
  SameOrAfter(Start(A), B, prec). Affects both engines identically.
- QA-002 HIGH: `starts/ends on or before|after <prec> of` ignores the precision
  on the interval-bound side — `_translate_starts_op`/`_translate_ends_op`
  hardcode DATE casts; inner `precision of` truncates only the right operand
  → false negatives at year/month (and silent day-collapse at hour/minute).
  e.g. `ends on or before year of @2012-12-31` → false (spec: true).

## Verified conformant / NOT A BUG (notable)
- `starts/ends same <prec> as Interval[...]` → SameAs(start, interval-as-
  singleton): start AND end must match → false for differing ends is correct
  (§9.24 + cql-to-elm qualifier semantics; right operand is NOT reduced to
  start unless trailing `start of` is present).
- Open-null unbounded bounds in same-family comparisons (false/null results
  consistent with CQL-09 unbounded doctrine); `Interval[X, null] same day as
  Interval[X, Y]` → false.
- Time-only intervals across same/same-or/on-or families — correct both
  engines at hour/minute precisions.
- Now()/Today()/TimeOfDay() arithmetic shapes (`Now()+1 year > Today()` true,
  duration/offset forms, tz-normalized Now(), ms truncation) — correct.
- Subtract: sub-second quantities (0.5 's', 1500 'ms'), offset-carrying
  operands preserve offset, DST spring-forward wall-clock instants compare
  correctly (`hours between @2024-03-10T01:00-05:00 and @2024-03-10T03:00-04:00`
  = 1, correct: 06:00Z vs 07:00Z), Time wraps modulo midnight, week arithmetic.
- Time ctor: 23:59:59.999 OK; 24:00 / sec 60 / ms 1000 / negative → null;
  null-gap → null; fractional Decimal args raise at translation (typed
  Integer params — correct).
- `same week ...` → null per spec week-variability note (pinned doctrine).
- Trailing `start of`/`end of` bound selectors work on the unqualified family.
- e2e FHIR: effectiveDateTime vs Measurement Period / Now()-offset where-
  clauses, define-alias boolean chains — parity clean and semantically
  correct on both engines (probe5.py).
- `Today() <= Now()` → null (implicit Date→DateTime precision uncertainty,
  consistent with pinned mixed-precision doctrine); day-precision form true.
- DateTime − DateTime has no CQL Subtract signature → BinderError both
  engines (spec-correct; use duration between).

## Baseline
No source changes made by QA. Probes only.
