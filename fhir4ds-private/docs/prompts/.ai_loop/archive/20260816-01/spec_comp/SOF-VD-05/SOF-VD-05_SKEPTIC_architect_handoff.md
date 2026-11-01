# Architect Handoff — SOF-VD-05 / SKEPTIC (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-05 — SQL-on-FHIR v2 `ViewDefinition.select.select` (nested
contentReference).
**Iteration**: 1.
**Open issues**: 0.
**Resolved-like statuses**: [].

## Audit Summary

- **Golden Standard** for SOF-VD-05: nested `select.select` is a full recursive
  `contentReference` to `ViewDefinition.select` (0..*); child selects inherit
  parent `forEach`/`forEachOrNull`/`repeat` focus, otherwise default `$this`;
  sibling select rowsets compose via Cartesian product; `ValidateColumns`
  algorithm step 2.1 rejects duplicate effective output column names across the
  recursive schema; `unionAll` inside a nested select composes branch schema
  with parent columns.
- **Implementation review**: `fhir4ds/viewdef/parser.py:_parse_select` (lines
  197–295) recursively parses nested `select`, present-null/non-array rejection
  via `_parse_object_array`; `parser._effective_output_names` (491–497) +
  `SQLGenerator._collect_select_output_schema` (1307–1322) share the same
  recursive schema collector used by the duplicate-name guard at parse time;
  `generator._hoist_nested_unions` (1799+) recursively hoists nested unionAll
  regardless of parent iterator. Architecture matches the documented Golden
  Standard.
- **SKEPTIC QA quality**: 8 distinct falsifiable hypotheses × 12 assertions.
  Covered all six chunk items (recursion cardinality, parent-context
  inheritance, default `$this`, parent+child column combination, duplicate-name
  validation, empty nested select). No "happy-path-only" testing detected.
  **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS. No source changes
  were made this iteration.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- (No new global knowledge entry required; the spec-confirmed
  `present-empty-array select.select: []` is accepted (matches 0..* cardinality)
  and is already documented as the NOT-A-BUG distinction from `repeat: []`
  rejection in AGENTS.md SOF-VD-07.)
