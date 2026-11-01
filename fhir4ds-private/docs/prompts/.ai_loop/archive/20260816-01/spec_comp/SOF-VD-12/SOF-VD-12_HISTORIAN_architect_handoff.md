# Architect Handoff — SOF-VD-12 / HISTORIAN (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-12 — profile activation consistency walkthrough.
**Iteration**: 1.
**Open issues**: 0.

## Audit Summary

- **Golden Standard**: profile activation must be consistent across
  parser, `from_dict`, `to_dict`, `SQLGenerator.generate`, and
  permissive `validate_view_definition` (warns, not raises). Shareable
  requires url/name/status/fhirVersion/column.type; Tabular forbids
  collection + non-primitive types AND inherits CanonicalResource
  status requirement.
- **Implementation review**: 8/10 probes pass outright. The 2 failures
  (H7 missing status, H8 wrong field name) were investigated and
  classified as test-side errors. Profile activation is consistent
  across all strict boundaries; permissive validate warns correctly.
- **HISTORIAN QA quality**: 10 probes systematically walking profile
  activation across 5 boundaries (parser/from_dict/to_dict/generate/
  validate). Both failures investigated before dismissal.
  **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- Confirmed: Tabular profile activation enforces CanonicalResource
  metadata (status) per AGENTS.md SOF-VD-12 HISTORIAN 2026-06-01.
  This is INTENDED behavior, not a bug. Future probes must include
  `status` when testing Tabular-valid views.
