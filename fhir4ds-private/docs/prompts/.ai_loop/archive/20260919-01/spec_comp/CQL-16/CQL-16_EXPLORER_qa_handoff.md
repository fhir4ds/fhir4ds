# QA Handoff — CQL-16 EXPLORER iteration 1 (2026-08-22)

## Personality
EXPLORER (fuzzer/abuser): boundary matrices, cross-type chaos, chained
families, list-extract interval selections, offset-transition meets.

## Probes run (fresh, .temp/qa/probe_cql16_explorer{,2}.py)
- Battery 1 (64 defines): exact-boundary matrices for meets / meets before /
  after / overlaps / overlaps before/after / on or after/before / intersect /
  included in / != / !~, with every open/closed bound combination at touching
  endpoints; DateTime millisecond meets (M05 ✓ true); DST-less offset
  transition meets (M06 probe-expectation error — actual instants overlapped);
  Decimal 1e-8 successor meets (M07 true, M08 false); degenerate [3,3]
  intervals across operators; intersect of three chained intervals (I05-I07
  ✓); closed-null sentinel regression (I08, B08 ✓); mixed-precision temporal
  precision-qualified overlaps/on-or (O11-O13, B02, B07 ✓ uncertainty where
  expected); First/Last interval selections through the part-2 family
  (L01-L05 ✓ — CQL-15 LIST_EXTRACT recognition holds for this family).
- Battery 2 (16 defines): Integer-vs-Decimal mixed interval bounds across the
  whole part-2 family, three engines (python-only, native-loaded, no-python).

## Findings
- QA-001 (HIGH, CONFIRMED): native `Interval::intersect` ignores
  effective-bound (Start/End successor/predecessor) normalization —
  `Interval[1,5) intersect Interval[4,8]` returns `[4,5)` in no-python mode
  vs spec/reference/Python `[4,4]` closed. interval.cpp:1439.
- QA-002 (HIGH, CONFIRMED): native `BoundValue::compare` type gate
  (interval.cpp:899) treats Integer vs Decimal bounds as incomparable (-2),
  producing null — and in several operators (overlaps, included in,
  overlaps before/after) a WRONG DETERMINISTIC FALSE — across the whole
  part-2 family in no-python mode (12/16 battery-2 divergences). Also breaks
  interval equality/equivalence (`[1,3] !~ [1.0,3.0]` native true, py false).

## Probe-expectation errors (not bugs)
- M06: my offset-transition intervals actually overlapped as instants (probe
  authored wrong endpoints); engine false is correct.
- M15: hour-precision successor steps by hour — meets true is correct.
- O04/O06: reference OverlapsBefore/AfterEvaluator is start-based strict
  (`before(start1, start2) and overlaps`); engine false is correct (verified
  against reference source fetched this session).

## Verified-clean regressions from prior launches
SKEPTIC sentinel-bound meets/on-or fixes and HISTORIAN Long/Quantity
sentinels all re-verified clean (MeetsNullLow, MeetsAfterNullHigh, B08, I08,
closed-null intersect bounds).

## Spec sources consulted
Reference IntersectEvaluator.java / OverlapsBeforeEvaluator.java /
OverlapsAfterEvaluator.java from cqframework/cql-engine (cloned this
session). CQL 1.5 §9.9 Intersect, §9.16-9.18, implicit conversions §2.

Handing off to FIX.
