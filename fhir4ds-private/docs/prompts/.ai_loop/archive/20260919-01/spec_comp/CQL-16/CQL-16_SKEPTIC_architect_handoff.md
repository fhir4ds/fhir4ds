# Architect Handoff — CQL-16 SKEPTIC iteration 1 (2026-08-22)

## Golden-standard invariants applied (this launch's diff)

1. Interval operator semantics belong in the UDF layer (Python authority +
   native mirror), not inline SQL — upheld: fixes at `udf/interval.py` +
   `interval.cpp`; translator change limited to dispatch, no SQLRaw/to_sql.
2. Reference-engine + official fixtures outrank ambiguous prose — upheld:
   QA-002/QA-004 reclassified INTENDED after reference/source verification
   rather than "fixing" conformant behavior.
3. Dual-engine lockstep — upheld: native mirror implemented, extension rebuilt
   and md5-verified deployed (b9164ff5254bc5944d86109dd5e2cf94, repo bundle +
   site-packages; ~/.duckdb stale cache cleared); 13-case parity test runs on
   py-fallback, native-loaded, and no-Python C++ connections.
4. No silent fallbacks / test hacks — the `in` fix dispatches by operand
   shape (interval-expression recognizer, incl. LIST_EXTRACT recursion), not
   by fixture values.

## Audit findings

- No CRITICAL/HIGH architecture findings in this launch's diff.
- Observation (LOW, no action): the interval-interval `in` branch duplicates
  ~15 lines of the `included in` lowering; future drift risk if included-in
  semantics change. Acceptable under minimal-footprint; flagged for a possible
  shared helper in a later refactor.
- Observation (LOW): sentinel bounds are int32 min/max for Integer; Long
  intervals with null closed bounds sentinel at int32 limits (matches Python
  `_cql_minimum_for_peer_bound` and reference minValue(Integer); Long-typed
  null-bound intervals are unpinned by fixtures). Documented in AGENTS.md.
- `_effective_start` vs `_sentinel_effective_start` duality: callers must pick
  deliberately; meets/on-or family now on sentinel variants, intersect /
  equals / others intentionally on raw effective semantics (matches reference
  per-function behavior). Documented in AGENTS.md doctrine.

## QA Enforcer Gate

QA was rigorous: 129 fresh dual-engine probes, spec text verified against live
cql.hl7.org 09-b, expectations cross-checked against reference engine Kotlin
source (Interval.kt start/end getters were decisive for the null-bound
semantics), LIST_EXTRACT operand-shape coverage per CQL-15 lesson, and honest
reclassification of 7 of 11 initial "failures" as probe-expectation errors.
RETRY_QA: false.

## Empirical validation (final tree state)

- Master gate (run_all, fresh): ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 (no ERROR retries needed), OVERALL 2832/2832.
- Focused: interval part1+2+3 parity 38/38 (10 in part2 incl. new test),
  wasm cpp surface + v2 expressions 152/152.

## Exit

Zero non-terminal CRITICAL/HIGH/MEDIUM issues; iteration 1 >= min_iterations 1.
exit_reason=CLEAN, workflow=null. Recommend HISTORIAN personality for the next
CQL-16 launch (per chunk cadence) focusing on: timing-phrase spellings of the
on-or/meets family over dynamic FHIR Period data, Long/Decimal null-bound
sentinels, and intersects of unbounded temporal intervals under measurement
period indirection.
