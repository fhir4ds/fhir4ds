# QA Handoff — CQL-17 EXPLORER

## Verdict: CLEAN — boundary-composition framing of the SKEPTIC evidence base

## Adjudications (all probe-expectation errors; 0 parity diffs)
1. point-from renders scalars as strings ('3') at the population surface.
2. `[1,9] properly includes [2,9]` → True — official fixture IntegerIntervalProperlyIncludesTrue
   (CqlIntervalOperatorsTest.xml:1796-1800) pins shared-END-bound proper inclusion as TRUE
   (properly includes = subset + NOT IDENTICAL, not strict interior).
3. `[Jan..Dec] same month as [Mar..Oct]` → False — interval same-as requires BOTH bounds
   equal at the requested precision (no fixture pins interval same-as; engine-consistent
   both engines; control with matching bounds → True).
Verified: point from non-unit interval → null (documented DuckDB-UDF boundary, spec says
run-time error — flagged-for-human per main-tree doctrine, unchanged); null properly
included in → False (ProperInNullRightFalse fixture); Interval(1,6] same as [2,6] → True
(effective-bounds doctrine).

