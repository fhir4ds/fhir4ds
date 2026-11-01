# QA Handoff — SOF-VD-05 HISTORIAN (iteration 1, 2026-08-23)

## Scope
Nested select recursion (`select.select` 0..*, SD contentReference recursion).
Personality: HISTORIAN — institutional-memory-targeted hunt for NEW divergences
beyond the SKEPTIC pass, plus regression re-verification of its 2 fixes.

## Spec anchors consulted
- v2 SD snapshot (`.temp/qa/sd-viewdefinition-v2.json`): `ViewDefinition.select.select`
  max=* via contentReference to `ViewDefinition#ViewDefinition.select`; select children
  = id/extension/modifierExtension/column/select/forEach/forEachOrNull/unionAll only.
- Local canonical clone `/mnt/d/sql-on-fhir-v2` (main): sof-js `validate.js`
  (additionalProperties:false, minItems:1), `index.js` (reference runtime — no repeat),
  models.fsh invariant sql-expressions (at most one of forEach/forEachOrNull/repeat).
- Official fixture snapshot `fhir4ds/viewdef/tests/spec_tests/` (repeat.json pins the
  array-of-paths repeat format: `"repeat": ["item"]`).

## Probe
`/mnt/d/fhir4ds/.temp/qa/sof_vd05_historian/probe.py` — 19/19 PASS.

Regression re-verification of SKEPTIC fixes at depth (R1–R4, all rejected correctly):
unknown field in depth-3 nested select; present-empty nested `select:[]`/`column:[]`;
unknown field inside a unionAll branch select.

NEW hypotheses verified conformant (N-series): forEachOrNull parent + child forEach
with empty-part row suppression (p3 contact w/o name drops the row; p2 null-preserved);
where evaluated per-focus under forEach; unionAll branch containing nested
select+forEach (row order unpinned by spec — set-equal); %rowIndex reset in nested
unionAll branch; nested select under repeat; constant referenced in depth-3 nested
where; duplicate-name rejection across nested-select/unionAll and at depth 4;
25-level identity nesting; %resource in nested column; nested unionAll branch
column-schema mismatch errors; native==fallback parity on all new compositions (P1–P3).

Probe-expectation errors corrected during the pass (all doctrine-consistent, NOT bugs):
- Declared `type:"string"` on a date-valued path (birthDate) is rejected by the runtime
  type guard — must declare `"date"` (fixtures do the same).
- `repeat` is an ARRAY of FHIRPath strings, not a scalar.
- unionAll rows are unordered per spec.
- Empty nested row-part suppresses the parent row (processing_model.md).

## Issues
- QA-001 LOW INTENDED: `fhirpath_repeat` only collects complex (dict) elements;
  primitive-yielding repeat paths (e.g. `["contact.name.given"]`) return empty on BOTH
  engines. The v2 SD does not define `repeat` at all; the legacy fixture suite only
  traverses object elements; upstream sof-js dropped repeat. No spec/fixture pin →
  documented INTENDED, no code change.

## Gate status
ViewDef pytest: 1185/1185. Master gate run post-QA (final-tree) recorded in
engineer_handoff/architect handoff. Binary md5s (repo == site-packages):
fhirpath 57d0634b6ee6eddee9fc06a1355bef5a, cql c5b22d58310c1eb7bafa17ce7877f989.
