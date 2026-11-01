# Architect Handoff — FP-11 evolution iteration 1, 2026-08-17

## Scope
Focused structural audit of the iteration-1 FIX delta (native evaluator
`formatDecimalNumber` rendering path + `powerDecimalExactText` exact-power
paths in `extensions/fhirpath/src/fhirpath/evaluator.cpp`) and the QA phase
quality gate. The broader campaign diff is covered by the two milestone code
reviews (code_review_findings.md, 2026-08-17).

## Golden Standard (invariants applied)
1. Dual-engine lockstep: every FHIRPath semantic change lands in BOTH the
   Python fallback and native evaluator.cpp with parity coverage (GLOBAL_RULES).
2. Decimal rendering doctrine: rational/exact results render 28-sig
   ROUND_HALF_EVEN exact text; transcendental VALUES stay binary64 with the
   canonical rendering = fixed expansion of Decimal(str(float)) shortest
   round-trip; scientific only for subnormals <1e-300 (FP-01/FP-11 pinned).
3. No silent fallbacks: a degrade path must be documented doctrine
   (exact-digit Integer powers) or a bounded anti-DoS guard, never an
   unexplained parity break.
4. Fixes must be general (class of input), not reproducer-specific.
5. After evaluator.cpp changes, the extension must be rebuilt AND redeployed
   (repo bundle, site-packages, ~/.duckdb caches).

## Audit findings
- QA-001 fix (expandScientificToFixed of shortestRoundTripText) satisfies
  invariants 1/2/4: general over the class "non-subnormal scientific double
  results"; parity test covers both engines; subnormal branch unchanged.
- QA-002 fix satisfies invariants 1/3/4: bail-outs removed or replaced by
  the bounded guarded-28 exact path; remaining `return false` degrades are
  documented (integer-base exact-digit doctrine, ±1e15 exponent anti-DoS,
  1M-char text cap, `1^e` short-circuit) — none is a silent parity break.
- Deployment verified: evaluator.cpp (13:03) → extension rebuilt (13:05) →
  repo bundle, site-packages, and ~/.duckdb v1.5.2 cache all 13:05.
- No test-driven hacks, no hardcoded reproducer constants in the engine
  (expected strings live only in the regression tests).

## QA Enforcer Gate
QA (EXPLORER) quality: HIGH. ~90 boundary/extreme dual-path cases with
spec citations, correct reconciliation against the pinned FP-01/FP-11
doctrines (transcendental values binary64; the defects were the rendering
truncation and the exact-power bail-outs), reproducers left in-tree. No
RETRY_QA.

## Empirical validation (this iteration)
- probes probe/probe2/probe3: zero divergences post-fix.
- test_math_parity.py: 14/14 (incl. 2 new focused regression tests).
- Conformance blocker gate: 2832/2832 (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47) — baseline held.

## State hygiene
Both issues VERIFIED and tombstoned in evolution.json; full evidence
archived to ARCHIVE_LOG.md ("FP-11 EXPLORER (2026-08-17, iteration 1)").

## Loop control
Zero non-terminal CRITICAL/HIGH/MEDIUM issues remain; iteration 1 >=
min_iterations (1). Clean exit eligible: exit_reason=CLEAN, workflow=null.
Recommended Fix Order for any follow-up: none from this iteration.

## Structural health note
The interrupted-session recovery pattern recurred: code fixes + rebuild
landed while state files lagged ("no fixes attempted"). Always trust the
working tree + artifact timestamps over the resume brief, and verify the
deployment trio before re-fixing.
