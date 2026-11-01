# Architect Handoff — FP-18 HISTORIAN iteration 1 (2026-08-18)

## Structural audit (scoped to this chunk's delta + §6.6/§6.7 surface)

Golden-standard invariants applied:
1. Dual-engine lockstep (Python fallback AND native evaluator.cpp, with parity
   coverage) — QA-002 fix landed natively only (the fallback was already
   correct) with a new permanent parity guard; QA-006 landed in core only
   (native was already correct); both directions verified by dual-path tests.
2. Extension binary hygiene — evaluator.cpp edit followed by rebuild AND
   redeploy; build artifact md5 == repo bundle md5
   (90ba446fb5dba8048b70da53e38cdde7). No stale-binary trap.
3. No test-driven hacks / no spec gaming — fixes are class-level (all Time
   arithmetic results, the INT32_MIN boundary), not fixture-shaped.
4. Fixtures outrank prose — verified: QA-004/QA-005 reclassifications cite
   specific fixture tests (testPlusDate13–22), logged in the AGENTS.md NOT A
   BUG registry.
5. Error-message contract coupling — no new execution-error messages
   introduced; `fhirpath_is_valid` classifications unchanged where expected
   ('-2147483648' True, '2147483648' False).

Findings:
- ARCH-001 (LOW, drift note, no action this launch): Integer literal-range
  logic now lives in three places (number_literal unsigned check, the
  polarity_expression 2^31 special case, and the native literal parser). The
  special case mirrors the existing Long-literal convention and is minimal,
  but a future generalization should validate signed literal ranges at the
  PolarityExpression boundary uniformly in one place.
- QA-001 deferral is structurally sound: the Python side already has the
  correct UCUM term-exponent algebra; the native side needs a port, not a
  redesign. Recommend a dedicated native-UCUM reconciliation chunk (same
  backlog as the prior launch's QA-007 binary/test drift, 172 known-failing
  FP-01/FP-11-era parity tests, count improved 183→172 with this launch's
  rebuild).

## QA Enforcer gate
QA was NOT lazy: 95 three-engine cases, spec text fetched from the normative
N1 page, SKEPTIC's 5 fixes re-verified, fixture XML consulted before logging
(three self-corrections QA-004/005/003 were dissolved by fixture/doctrine
evidence — the correct outcome). No RETRY_QA.

## Validation
- test_fp18_math_operators.py 66/66 (was 57; +9 historian tests).
- Full fhirpath tree: 1829 passed / 172 failed — all in the documented
  pre-existing drift family (prior-launch QA-007; verified pre-launch-binary
  equivalent). No new failures.
- Conformance master gate: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 — OVERALL 2832/2832. No regression.

## State
All 6 issues terminal (2 RESOLVED, 3 INTENDED, 1 DEFERRED). Zero non-terminal
CRITICAL/HIGH/MEDIUM. iteration 1 >= min_iterations 1 → CLEAN exit.
Detail archived to ARCHIVE_LOG.md; GLOBAL_KNOWLEDGE.md updated (Evolution
Statistics row + Personality Effectiveness Log); AGENTS.md updated (FP-18
HISTORIAN section + NOT A BUG registry).

## Recommended fix order (next chunk)
1. Native UCUM term-exponent port (QA-001 deferral).
2. Binary/test drift reconciliation chunk (QA-007 family, 172 tests).
