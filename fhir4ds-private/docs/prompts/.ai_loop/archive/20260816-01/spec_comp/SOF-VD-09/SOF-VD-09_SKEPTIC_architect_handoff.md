# Architect Handoff — SOF-VD-09 / SKEPTIC (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-09 — `where.path` / `where.description`.
**Iteration**: 1.
**Open issues**: 0.

## Audit Summary

- **Golden Standard**: where constraints require exact singleton Boolean
  true; false/empty/null/string/numeric exclude; where.path required
  string; where.description optional markdown; constants/complex
  FHIRPath resolve before SQL; select-level where supported; root scope
  preserved.
- **Implementation review**: `fhir4ds/viewdef/types.py`
  `validate_where_conditions()` + `fhir4ds/viewdef/generator.py`
  `fhirpath_json(...) = '[true]'` SQL boundary. All 12 hypotheses tested;
  11 passed outright, 1 (H3) was a hypothesis error confirmed by
  re-reading the exact-singleton-true rule.
- **SKEPTIC QA quality**: 12 falsifiable hypotheses covering all 7 chunk
  items. **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- Confirmed: SOF-VD-09 exact-singleton-true semantics (a bare `where:
  active` returning `false` EXCLUDES the row) remain aligned with
  AGENTS.md SOF-VD-09 (2026-05-20 / 2026-06-01).
