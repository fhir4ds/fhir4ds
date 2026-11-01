# Architect Handoff — SOF-VD-07 / EXPLORER (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-07 — `select.repeat` pathological-input probe.
**Iteration**: 1.
**Open issues**: 0.

## Audit Summary

- **Golden Standard**: repeat must handle deep nesting (300+ levels),
  large flat arrays (1000+), unicode/emoji, malformed FHIRPath
  rejection, `$this` self-traversal cycle guards, and overlapping-path
  node DE-DUPLICATION (per official `repeat.json` "item and answer.item"
  which expects 6 de-duplicated rows when 1.1.1 is reachable via two
  paths).
- **Implementation review**: all pathological probes pass after
  classifying 2 initial failures as test-harness / hypothesis errors
  (E1 fixture construction off-by-one; E3 hypothesis incorrectly
  expected duplicate preservation). De-duplication matches official
  spec_test. Deep iterative traversal handles 300+ levels without
  recursion limits.
- **EXPLORER QA quality**: 10 distinct pathological inputs; both
  failures investigated against the official spec_test fixtures and
  resolved as INTENDED before being dismissed. **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- Confirmed: official `repeat.json` "item and answer.item" (6 expected
  rows, not 7) is the authoritative evidence that repeat DE-DUPLICATES
  overlapping-path node hits. The project's documented "union duplicate
  node hits across paths" (AGENTS.md SOF-VD-07 SKEPTIC 2026-05-20) is
  spec-correct. Add this as a NOT-A-BUG confirmation.
