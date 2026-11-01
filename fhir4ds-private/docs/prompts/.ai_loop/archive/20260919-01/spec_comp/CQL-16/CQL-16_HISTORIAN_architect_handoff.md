# Architect Handoff — CQL-16 HISTORIAN iteration 1 (2026-08-22)

## Golden-standard invariants applied (this launch's diff)

1. Interval operator semantics belong in the UDF layer (Python authority +
   native mirror), not inline SQL — upheld: all fixes in `udf/interval.py` +
   native sentinel tables; translator untouched.
2. Reference-engine + official fixtures outrank prose — upheld: expectations
   verified against fetched reference sources (Interval.kt start/end getters,
   Constants.MIN_LONG/MAX_LONG/MAX_DECIMAL, MinValueEvaluator,
   OverlapsEvaluator.kt). HISTORIAN correctly re-verified the SKEPTIC fixes
   and hunted new ground instead of re-running old probes.
3. Dual-engine lockstep — upheld: BOTH native sentinel tables updated
   (`interval.cpp` sentinel_start/end_bound AND `cql_extension.cpp`
   Minimum/MaximumForIntervalPointType), plus Python `_successor`/
   `_predecessor` int64 overflow guards and `intervalMeetsBefore` isMax
   parity. Extension rebuilt; md5 **3c0cebec785fb36d8030d37d71c65de4**
   verified across build output, repo bundle, and site-packages;
   `~/.duckdb` stale cache cleared; re-verified through no-Python
   connections. A latent py/native meets-before overflow divergence (temporal
   max sentinel) was found and closed during remediation.
4. No silent fallbacks / test hacks — sentinel selection is magnitude/unit
   driven, not fixture driven.

## Audit findings

- No CRITICAL/HIGH architecture findings in this launch's diff.
- Observation (LOW, documented in AGENTS.md): the native layer carries TWO
  parallel sentinel tables (interval.cpp for the meets/on-or family,
  cql_extension.cpp for intervalStart/intervalEnd) that must be edited in
  lockstep; drift risk noted for a future shared-helper refactor.
- Documented boundary (LOW): int32-range Long peers (e.g. `Interval[5L, null]`)
  keep Integer sentinels because authored `L`-ness is erased at translation;
  unpinned by fixtures.

## QA Enforcer Gate

QA was rigorous: ~110 fresh dual-engine probes across four batteries, live
reference-source verification (fetched this session), honest separation of
probe-expectation errors from real divergences (6 of 10 initial "failures"
were probe errors), regression re-verification of both SKEPTIC fixes, and
coverage of the architect-suggested HISTORIAN directions (Long/Decimal
sentinels, unbounded temporal intersects, measurement-period indirection).
RETRY_QA: false.

## Empirical validation (final tree state, fresh run)

- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47 (no ERROR retries needed), OVERALL 2832/2832 — baseline holds.
- Focused: interval part1+2+3 parity 39/39 (incl. new 16-define HISTORIAN
  test across py-fallback / native-loaded / no-Python engines);
  wasm cpp surface + v2 expressions 152/152.

## Handoff compression

SKEPTIC's fixes (interval-interval `in` dispatch; closed-null sentinel bounds
in meets/on-or family) re-verified clean. HISTORIAN found 2 new MEDIUM
spec violations — Long null-bound sentinels pinned at int32, and missing
Quantity sentinels — both fixed dual-engine per reference Interval.kt
semantics, plus a latent meets-before overflow parity gap closed. Regression
coverage added; conformance baseline intact.

## Exit

Zero non-terminal CRITICAL/HIGH/MEDIUM issues; iteration 1 >= min_iterations 1.
exit_reason=CLEAN, workflow=null. Next CQL-16 launch (if scheduled) should
try EXPLORER/SPECIALIST: fuzzing the new sentinel paths (mixed-unit quantity
interval null bounds, Long/Decimal mixed-point-type operands, nested-list
interval operands through the part-2 families).
