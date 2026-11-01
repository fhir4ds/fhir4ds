# Architect Handoff — CQL-16 EXPLORER iteration 1 (2026-08-22)

## Golden-standard invariants applied (this launch's diff)

1. Interval operator semantics belong in the UDF layer (Python authority +
   native mirror), not the translator — upheld: both fixes are in
   `extensions/cql/src/cql/interval.cpp`; translator untouched.
2. Reference engine + fixtures outrank prose — upheld: expectations verified
   against fetched reference sources (IntersectEvaluator.kt
   `new Interval(max, true, min, true)`; OverlapsBefore/AfterEvaluator.kt
   start-based strict; §2 implicit numeric conversions).
3. Dual-engine lockstep — upheld: both defects were native-only (Python was
   already spec-correct); new 10-case × 3-engine regression test pins
   py-fallback / native-loaded / no-Python parity. Extension rebuilt and
   md5 **87e4f6e866bfbc7151eb42ff779c9fd1** verified identical across build
   output, repo bundle, and site-packages; ~/.duckdb cache cleared; fix
   re-verified through a fresh no-Python connection.
4. No silent fallbacks / fixture hacks — the cross-numeric compare is a
   general §2 rule (long double), not per-operator patching; the intersect
   fix reuses the shared successor/predecessor bound helpers.

## Audit findings

- No CRITICAL/HIGH architecture findings in this launch's diff.
- LOW observation (documented, not fixed): when `predecessor_bound`/
  `successor_bound` overflows at a temporal max/min sentinel with an OPEN
  finite bound, native intersect keeps the raw open bound while the Python
  parse-time normalization treats it as unbounded-closed; divergence exists
  only at the 9999-12-31T23:59:59.999 / 0001-01-01T00:00:00.000 open-bound
  extremes — unpinned by fixtures, noted in AGENTS.md.
- Blast-radius check: the `BoundValue::compare` fix also (correctly) repairs
  `equals_nullable`, `except_of`, `union_of`, and precision variants for
  cross-numeric operands — all were equally wrong before; conformance gate
  confirms no regressions.

## QA Enforcer Gate

QA was rigorous: 80 fresh three-engine probes across two batteries,
boundary/open-closed matrices for the full chunk operator list, chained
intersect families, First/Last interval selections (CQL-15 LIST_EXTRACT
recognition verified for this family), offset-transition and 1e-8 successor
meets, honest separation of 3 probe-expectation errors (M06/M15/O06) from
real divergences, and re-verification of both SKEPTIC and HISTORIAN fixes.
RETRY_QA: false.

## Empirical validation (final tree state, fresh run)

- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47 (no ERROR retries needed), OVERALL 2832/2832 — baseline holds.
- Focused: interval part1+2+3 parity + interval UDFs 97/97; v2 expressions
  + arithmetic-part2 + logical parity 221/221; both EXPLORER probe
  batteries zero divergences post-fix.

## Handoff compression

EXPLORER found 2 native-only HIGH spec violations the two prior
personalities missed because their probes stayed in same-numeric-type,
closed-bound territory: (1) `BoundValue::compare` flagged Integer-vs-Decimal
interval bounds incomparable, cascading NULLs and wrong deterministic FALSEs
across the entire part-2 family in no-Python mode; (2) native `intersect`
ignored effective Start/End bound normalization for open bounds. Both fixed
in interval.cpp per reference semantics, extension rebuilt/deployed
(md5 87e4f6e8...), regression-tested across three engines, gate intact.

## Exit

Zero non-terminal CRITICAL/HIGH/MEDIUM issues; iteration 1 >= min 1.
exit_reason=CLEAN, workflow=null. CQL-16 chunk now covered by three
personalities (SKEPTIC, HISTORIAN, EXPLORER) — recommend closing the chunk.
