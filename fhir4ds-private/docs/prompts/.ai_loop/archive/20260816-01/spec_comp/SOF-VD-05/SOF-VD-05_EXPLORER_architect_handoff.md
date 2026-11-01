# Architect Handoff — SOF-VD-05 / EXPLORER (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-05 — SQL-on-FHIR v2 `ViewDefinition.select.select` (nested
contentReference).
**Iteration**: 1.
**Open issues**: 0.
**Resolved-like statuses**: [].

## Audit Summary

- **Golden Standard** verified against the normative spec's `Process(S, N)`
  recursive algorithm and `ValidateColumns(S, C)` recursion:
  1. Cartesian-product semantics compose parent column bindings, sibling
     nested-select rowsets, and unionAll branch rowsets. (validated: E1, E4, E5,
     E6, E8.)
  2. Empty rowset in any Cartesian factor → empty total rowset. (validated: E5
     empty case, E8.)
  3. forEachOrNull null row participates in Cartesian as a single-row rowset.
     (validated: E5 populated case, cascading from earlier HISTORIAN I2b.)
  4. Recursive `ValidateColumns` enforces duplicate-name across all depths.
     (validated: E7 parity for duplicate-name-deep.)
  5. Column Ordering preserved: parent cols → nested cols → unionAll cols.
     (validated: E1, E6.)
  6. Recursive `where` is scoped to the parent iterator focus, not the root
     resource. (validated: E2 — Jones branch filtered by nested `where`.)
- **Implementation review**: Architecture matches Golden Standard.
  - `fhir4ds/viewdef/generator.py:1639-1666` — nested-select recursion passes
    parent forEach/forEachOrNull context down to child selects via
    `nested_null_var` / `current_var`.
  - `fhir4ds/viewdef/generator.py:1799+` (`_hoist_nested_unions`) — handles
    default-`$this`, iterator-parent, and unionAll-inside-nested-select cases
    uniformly.
  - `fhir4ds/viewdef/parser.py:482-511` — parser-level `ValidateColumns` mirror
    uses same recursive `_effective_output_names` collector as the generator.
- **EXPLORER QA quality**: 11 assertions across 8 pathological batteries
  including deeply-mixed iterator+sibling+nested-unionAll combinations,
  nested-where recursion, forEach-only nested entries, multi-collection
  forEach inside nested selects, sibling forEachOrNull+forEach Cartesian
  edge cases, empty-column+unionAll nested, parser/from_dict parity across 3
  pathological shapes, and zero-row Cartesian. Comprehensive chaos coverage.
  **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS. No source changes
  made this iteration.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- No new global knowledge entry required. EXPLORER-verified behaviors are
  consistent with the spec's `Process(S, N)` algorithm and the recursive
  architecture already documented for earlier SOF-VD chunks.
