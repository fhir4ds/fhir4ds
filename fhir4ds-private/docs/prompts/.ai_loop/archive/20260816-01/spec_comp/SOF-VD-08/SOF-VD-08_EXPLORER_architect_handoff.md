# Architect Handoff — SOF-VD-08 / EXPLORER (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-08 — `select.unionAll` pathological-input probe.
**Iteration**: 1.
**Open issues**: 0.
**Deferred**: QA-001 (where-only unionAll branch — spec-silent, benign no-op).

## Audit Summary

- **Golden Standard**: unionAll must handle pathological inputs gracefully:
  many branches, deep nesting, empty branches, collection columns,
  unicode values, malformed members, repeat branches, and branch-local
  where isolation.
- **Implementation review**: 9/10 pathological probes pass. The single
  exception (QA-001) is a where-only branch that produces a benign
  `SELECT NULL WHERE FALSE` no-op. The spec does not mandate rejecting
  this shape, so DEFERRED is appropriate. No data corruption, no crash.
- **EXPLORER QA quality**: 10 distinct pathological inputs covering
  branch count, depth, emptiness, types, unicode, and error paths.
  QA-001 investigated and classified, not dismissed blindly.
  **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues. QA-001 is DEFERRED (terminal).

## Global Knowledge Update

- Add to NOT-A-BUG Registry: a `unionAll` branch containing only `where`
  (no rowset producer) generates `SELECT NULL WHERE FALSE` (0 rows).
  This is benign and spec-silent; not a conformance blocker. Future
  iterations may tighten parser validation if the spec adds an explicit
  rowset-producer requirement.
