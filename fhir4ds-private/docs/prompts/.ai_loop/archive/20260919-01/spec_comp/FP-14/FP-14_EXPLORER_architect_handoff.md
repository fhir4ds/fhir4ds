# FP-14 EXPLORER Architect Handoff (2026-08-18, iteration 1)

## Scope audited
Uncommitted delta of this launch: `fhir4ds/fhirpath/engine/nodes.py`
(FP_TimeBase fraction-compare helpers + componentwise compare/equals
equal-precision branches; FP_Time manual time-object fallback) and
`fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`
(new 13-case dual-path regression).

## Golden-standard invariants applied
1. §6.2 comparisons must use decimal fraction semantics on authored digits —
   never a lossy intermediate (datetime µs, binary64). The fix satisfies this
   generically (digit-string compare), not per-fixture.
2. Dual-engine lockstep: native already implements the same semantics
   (FP-14 HISTORIAN frac_digits); this launch closed the Python side only —
   correct direction, no extension rebuild required.
3. No new duplicated semantic tables: the helpers live once in FP_TimeBase,
   shared by Date/DateTime/Time — consistent with the REV-002 drift-avoidance
   family.

## Findings
- QA-001/QA-002/QA-003 RESOLVED and verified (probe 0/23 diffs, parity file
  107 passed, fhirpath tree 1909, conformance 2832/2832).
- ARCH-001 (LOW, DEFERRED): `engine/invocations/collections.py` orderBy
  helpers still call `_getDateTimeInt()` and can mix FP_Date multiplier-sum
  ints with FP_DateTime epoch timestamps (the QA-003 scale family), and
  truncate sub-µs fractions. Pre-existing, outside §6.2 operator scope, no
  fixture pins mixed-type orderBy; fold into any future collections-ordering
  chunk.
- QA Enforcer Gate: PASS — EXPLORER probed the mandate areas (boolean/iif
  chaining, converted operands, 28-digit/int64 extremes, tz boundary
  crossings, 1–9-digit sub-second vs peers, quantity tolerances, Unicode
  code-point ordering, heterogeneous where/repeat, arithmetic feeds,
  is_valid) and reused the interrupted probe correctly after fixing its
  harness artifact. No RETRY_QA.

## Structural health
Good. The compare path now has a single canonical componentwise+fraction
algorithm in FP_TimeBase; residual duplication risk is `_getDateTimeInt`
callers outside comparisons (ARCH-001 only).

## Exit
Clean exit at min_iterations=1: zero non-terminal CRITICAL/HIGH/MEDIUM
issues.
