# QA Handoff — SOF-VD-05 / SKEPTIC (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-05 — SQL-on-FHIR ViewDefinition.select.select (Nested select
contentReference).
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). `select.select` contentReference is to `ViewDefinition.select`
(recursion 0..*). Sibling select rowsets compose via Cartesian product; child
selects inherit parent `forEach`/`forEachOrNull` focus; default context is
`$this` when no row generators are present; `ValidateColumns` algorithm step 2.1
throws "Column Already Defined" for duplicate effective output names.
**Personality**: SKEPTIC (Hypothesis Attacker).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd05_skeptic_2026_07_03_fresh/probe.py`
**Result**: **PASS — 12/12 assertions across 8 hypotheses; 0 issues.**

## Hypotheses Tested (all rejected)

- **H1** present-null nested `select` rejected at parser & `ViewDefinition.from_dict` (2 cases) — PASS.
- **H2** non-array nested `select` (string + object) rejected — PASS (2 cases).
- **H3** duplicate effective output name across parent column + nested-select column rejected at parser & `from_dict` (2 cases) — PASS.
- **H4** empty nested `Select(column=[], select=[])` with parent column behaves as identity rowset (parent row preserved, single output column) — PASS.
- **H5** 50-deep recursive nested select chain compiles and executes (1 row × 50 columns) — PASS.
- **H6** child select inherits parent `forEach="name"` focus; child column `given.first()` resolves against the unnested name element (returns `("Smith", "John")`) — PASS.
- **H7** `unionAll` inside a nested select combines parent column (`id`) + branch schema `{v, x}` producing `[id, v, x]` with 2 rows (one per branch) under default `$this` context — PASS.
- **H8** present-empty-array `select.select: []` accepted at parser & `from_dict` (current behavior; equivalent to absence) — PASS (informational; not a bug).

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd05_skeptic_2026_07_03_fresh/probe.py`

## Notes

- All 8 hypotheses empirically rejected; no real bugs found.
- Spec-confirmed behavior (NOT A BUG): a present-empty-array `select.select: []`
  is accepted (treated as no nested selects). This matches the
  `require_non_empty=False` default for nested `select` in `_parse_object_array`
  and the SQL-on-FHIR "0..*" cardinality (zero is a valid count). Distinct from
  the SOF-VD-07 precedent for `select.repeat: []` which IS rejected because
  `repeat` is a required-presence directive when the field appears.
- All earlier SOF-VD-05 fixes (EXPLORER fresh-rerun recursive where validation
  in `Select.to_dict()`, HISTORIAN recursive unionAll hoisting under default
  `$this`, SKEPTIC row-composition layering for forEachOrNull + child select)
  remain intact.
