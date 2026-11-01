# Architect Handoff — SOF-VD-05 / HISTORIAN (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-05 — SQL-on-FHIR v2 `ViewDefinition.select.select` (nested
contentReference).
**Iteration**: 1.
**Open issues**: 0.
**Resolved-like statuses**: [].

## Audit Summary

- **Golden Standard** for SOF-VD-05 verified against the normative spec
  (https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html):
  1. `select.select` is a 0..* recursive contentReference to
     `ViewDefinition.select`. (validated: `parser._parse_select` recurses.)
  2. `Process(S, N)` step 1: focus = parent iterator result; default `[N]`
     (confirms `$this` default). (validated: HISTORIAN I2, I3.)
  3. `Process(S, N)` step 2.3: nested `select` rows are Cartesian-combined with
     column bindings and sibling rowsets. (validated: HISTORIAN I4.)
  4. `ValidateColumns` step 3 throws "Column Already Defined" recursively.
     (validated: HISTORIAN I5 across parent+child, nested+nested-sibling, and
     3-level-deep collisions, at both parser and `from_dict` boundaries.)
  5. Column Ordering: parent cols → nested cols → unionAll cols.
     (validated: HISTORIAN I1 `[a, b, c]`.)
  6. forEachOrNull null-row binding cascades NULLs into child columns.
     (validated: HISTORIAN I2b `(NULL, NULL)`.)
- **Implementation review**: Architecture matches Golden Standard.
  - `fhir4ds/viewdef/parser.py:482-511` — recursive `_effective_output_names`
    used by parser-level `ValidateColumns` mirror.
  - `fhir4ds/viewdef/generator.py:1307-1322` (`_collect_select_output_schema` +
    `_collect_select_non_union_schema`) — same recursive algorithm reused by
    duplicate-name validation, column-order emission, and unionAll branch
    schema comparison.
  - `fhir4ds/viewdef/generator.py:1799+` (`_hoist_nested_unions`) — recursive
    hoisting handles default-`$this` and iterator parents uniformly.
- **HISTORIAN QA quality**: Systematic 8-test / 13-assertion spec-section walk
  covering all 6 chunk items with explicit normative citations. Cartesian
  semantics, default-`$this` context, parent-iterator inheritance, null-row
  binding cascade, recursive duplicate-name validation, and empty-combination
  behavior all empirically verified end-to-end (parser → dataclass → SQL
  generation → DuckDB execution). No "happy-path-only" testing. **RETRY_QA: false.**
- **Regression check**: No source changes made this iteration. ViewDefinition
  pytest 1055/1055 (verified in SKEPTIC architect phase earlier this run).

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- No new global knowledge entry required. The HISTORIAN-verified
  no-declared-type boolean serializes as string token `'true'`/`'false'`
  behavior is consistent with the spec note ("It is reasonable for an
  implementation to treat any non-specified types as strings") and matches the
  generator's existing primitive-string fallback already documented for
  earlier SOF-VD chunks.
