# Architect Handoff — SOF-VD-11 / EXPLORER (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-11 — View Runner pathological-input probe.
**Iteration**: 1.
**Open issues**: 0.

## Audit Summary

- **Golden Standard**: runner must handle pathological inputs: deep JSON,
  large batches, unicode, malformed JSON (rejected upstream by DuckDB),
  type mismatches, SQL injection attempts, and complex FHIRPath.
- **Implementation review**: 8/10 pathological probes pass outright. The
  2 failures were investigated and classified as test-harness / hypothesis
  errors (E4 malformed JSON is rejected by DuckDB before the runner sees
  it; E9 used wrong getReferenceKey syntax). No data corruption, no
  crashes on valid input, type/cardinality guards all fire correctly.
- **EXPLORER QA quality**: 10 distinct pathological inputs including
  security (SQL injection) and scale (1000 resources). Both failures
  investigated against official spec_tests before dismissal.
  **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- Confirmed: `getReferenceKey()` is a method on a Reference node
  (e.g., `link.other.getReferenceKey()` or
  `link.other.getReferenceKey(Patient)`), NOT a function taking a path
  argument. Per official `fn_reference_keys.json`. Add to NOT-A-BUG
  Registry for future EXPLORER probes.
- Confirmed: DuckDB rejects malformed JSON at INSERT time (before view
  execution), so the runner never sees malformed JSON in the resource
  column. Probes testing malformed-JSON handling must use a different
  transport or expect the DuckDB-level error.
