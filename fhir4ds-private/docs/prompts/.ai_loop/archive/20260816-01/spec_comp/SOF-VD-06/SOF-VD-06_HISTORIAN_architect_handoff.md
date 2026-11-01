# Architect Handoff — SOF-VD-06 / HISTORIAN (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-06 — `forEach` / `forEachOrNull` systematic spec walkthrough.
**Iteration**: 1.
**Open issues**: 0.

## Audit Summary

- **Golden Standard**: official SQL-on-FHIR v2 `foreach.json` (13 cases)
  defines the canonical forEach/forEachOrNull semantics. The runner must
  produce the same row multiset as `expect[]` (row ORDER is not a
  conformance signal per AGENTS.md / SOF-VD-07 EXPLORER 2026-06-01).
- **Implementation review**: all 13 official cases pass when compared as
  multisets. Row multiplication, empty-collection suppression,
  null-row preservation, sibling-select column preservation,
  nested-iterator row composition, and unionAll + iterator composition
  all match the official `expect[]` exactly.
- **HISTORIAN QA quality**: complete systematic walkthrough of the
  official fixture set, covering all 6 chunk items. No "happy-path-only"
  testing — exercised empty, null, nested, and combined cases.
  **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- Confirmed: the project's interpretation that physical DuckDB row order
  is not a conformance signal remains valid for SOF-VD-06. The official
  `foreach.json` fixtures pass as multisets. No new global entry.
