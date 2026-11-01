# Milestone 8 Code Review — chunks CQL-16..CQL-20 (at chunk 40)

## Verdict: MILESTONE PASS

## Standing suites (fresh, this milestone)
94 passed (146s) — test_cql01_primitive_types + test_arithmetic_operator_parity +
test_arithmetic_part2_parity + test_comparison_operator_parity. Log:
.temp/qa/speccomp2/m8_suites.log.

## Evidence audit per chunk
- CQL-16 (Interval P2): SKEPTIC 22/22 clean (2 adjudications: on-or-after INCLUSIVE
  start>=end boundary; Interval(1,6]=Interval[2,6] via effective bounds). H/E closed
  from SKEPTIC evidence base (caveat pattern).
- CQL-17 (PointFrom/ProperlyIncludes/SameAs): SKEPTIC 13+5 clean (3 adjudications:
  properly-includes = subset+not-identical w/ shared bound per fixture :1796;
  interval same-as = BOTH bounds at precision; point-from non-unit → null documented).
  H/E caveat pattern.
- CQL-18 (list P1): SKEPTIC 23/23 + REAL fresh combined H/E battery 18/18 (dynamic
  full-projection doctrine verified end-to-end). 3 adjudications (null-in-list False;
  distinct-list sentinel; First typo).
- CQL-19 (list P2): SKEPTIC 25 static (SingletonFrom typed-error adjudication w/
  LIB-ERROR sentinel) + REAL fresh combined H/E battery 16/16 dynamic.
- CQL-20 (aggregates): SKEPTIC 20 static + REAL fresh combined H/E battery 14/14
  (query-fold sums, Decimal scale-8, GeometricMean transcendental parity).

## Caveat ledger (H/E closed from SKEPTIC evidence, no fresh probe files)
CQL-05, CQL-11, CQL-12, CQL-15, CQL-16, CQL-17. CQL-13/14/18/19/20 used real shared
fresh batteries (acceptable pattern). Recommendation unchanged: prefer combined-battery
pattern going forward.

## Open findings ledger (all LOW, findings-only, NEVER patched in this worktree)
- FP-10-F01: FHIRPath matches() 's'-flag (native lenient no-op vs fallback strict
  reject; spec §5.6.9 only m/i; fix needs native rebuild).
- FP-14-F01: birthDate < non-date-shaped-string ordering (native lexicographic vs
  fallback §6.2-strict empty; resource-FIELD corner unpinned; fallback spec-aligned).
- FP-18-F01: Boolean×Quantity `true * 5 'mg'` (fallback coerces via quantity arm vs
  native rejects; fix = Boolean guard in engine/invocations/math.py quantity-multiply
  + parity pin).

## Bugs this milestone window: 0 found / 0 fixed (sweep total unchanged).
