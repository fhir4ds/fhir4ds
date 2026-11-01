# Architect Handoff — SOF-VD-11 / HISTORIAN (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-11 — View Runner systematic spec walkthrough.
**Iteration**: 1.
**Open issues**: 0.

## Audit Summary

- **Golden Standard**: the runner must produce spec-expected rows for
  official example fixtures across basic projection, resource keys,
  reference keys, boundary functions, row indexing, and combinations.
- **Implementation review**: 38/40 official cases pass. The 2 fn_boundary
  decimal cases were investigated and classified as test-harness
  normalization artifacts (NaN vs None for DOUBLE NULL). All actual
  values are spec-correct.
- **HISTORIAN QA quality**: complete multi-file systematic walkthrough
  (6 fixture files, 40 cases). Both failures investigated before
  dismissal. **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- Add to NOT-A-BUG Registry: DuckDB DOUBLE SQL NULL renders as pandas
  `float('nan')`, while spec_test fixtures encode absent decimal values
  as JSON `null` → Python `None`. Probes comparing decimal column output
  must treat NaN and None as equivalent. This is a transport/representation
  difference, not a behavioral bug. Applies to fn_boundary decimal
  lowBoundary/highBoundary and any future DOUBLE-column absent-value
  comparison.
