# Architect Handoff — SOF-VD-06 / SKEPTIC (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-06 — SQL-on-FHIR v2 `forEach` / `forEachOrNull`.
**Iteration**: 1.
**Open issues**: 0.
**Resolved-like statuses**: [].

## Audit Summary

- **Golden Standard** for SOF-VD-06: `forEach` 0..1 FHIRPath multiplies rows
  one per collection item and produces zero rows when the collection is
  empty; `forEachOrNull` 0..1 produces a single null-valued row when the
  collection is empty, where columns INSIDE the forEachOrNull select stanza
  become NULL and parent-resource columns projected through SIBLING selects
  keep their values (per official `foreach.json` "forEachOrNull: null case"
  and "forEachOrNull: basic"). Nested columns resolve against the iterated
  item context; built-in `%context`/`%resource`/`%rootResource`/`%rowIndex`
  resolve correctly inside iterated contexts; `forEach`/`forEachOrNull`/
  `repeat` are mutually exclusive; present JSON null for either iterator
  field is rejected as invalid FHIR JSON shape.
- **Implementation review**: iterator semantics concentrated in
  `fhir4ds/viewdef/generator.py` (select rowset emission, `fhirpath_json`
  invocation, `%rowIndex`/`%resource`/`%rootResource` substitution) and
  `fhir4ds/viewdef/parser.py` + `types.py` (mutual exclusion and
  present-null rejection). Matches the documented Golden Standard. All
  prior SOF-VD-06 fixes verified intact (HISTORIAN 2026-05-20/06-01,
  SKEPTIC 2026-05-20/06-01, EXPLORER 2026-05-20/06-01).
- **SKEPTIC QA quality**: 10 falsifiable hypotheses × 1 informational
  finding. Covered all six chunk items (row multiplication, empty
  suppression, null-row preservation, nested-column focus, mutual
  exclusion, present-null rejection, %rowIndex in iterated context,
  Cartesian composition). H3 finding was verified against official
  spec_tests and classified INTENDED, not a regression.
  **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- No new global knowledge entry required. Confirmed the official
  spec_tests `foreach.json` place parent columns in a SIBLING select
  (not inside the forEachOrNull stanza), so the project's "all columns
  inside the forEachOrNull null-row are NULL" interpretation is
  consistent with the spec's "the row produced will have null values"
  language and with prior AGENTS.md SOF-VD-05/06 entries.
