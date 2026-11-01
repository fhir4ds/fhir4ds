# QA Handoff — SOF-VD-09 / SKEPTIC (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-09 — SQL-on-FHIR Key Elements Where (`where.path`,
`where.description`).
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). `where` 0..* root-level FHIRPath constraints; every constraint
must evaluate to singleton Boolean `true` for inclusion (`fhirpath_json(...)
= '[true]'`); false, empty, null, strings, numerics all EXCLUDE; `where.path`
1..1 required string; `where.description` 0..1 markdown metadata; constants
and complex FHIRPath resolve before SQL generation; select-level where also
supported.
**Personality**: SKEPTIC (Hypothesis Attacker).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-09_SKEPTIC/probe.py`
**Result**: **PASS — 11/12 hypotheses; 0 bugs. 1 hypothesis error (H3).**

## Hypotheses Tested

- **H1** where `active = true` includes matching rows — PASS.
- **H2** where `active = false` excludes — PASS.
- **H3** where `active` (bare existence) — initial FAIL. Hypothesis
  expected `{p1,p2,p4}` but got `{p1,p4}`. **Hypothesis was wrong**: p2
  has `active=false` (boolean), which per AGENTS.md SOF-VD-09 exact-
  singleton-true semantics EXCLUDES the row. The implementation is
  correct; bare `active` returning `false` is not inclusion.
  Classified hypothesis error, not a bug.
- **H4** non-boolean where (string `'male'`) excludes — PASS.
- **H5** multiple where clauses AND — PASS.
- **H6** where with constants — PASS.
- **H7** where.description retained (round-trip) — PASS.
- **H8** missing where.path rejected — PASS.
- **H9** non-string where.description rejected — PASS.
- **H10** where at select level accepted — PASS.
- **H11** non-boolean numeric where excludes — PASS.
- **H12** where with complex FHIRPath (`identifier.where(...).exists()`) — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-09_SKEPTIC/probe.py`

## Notes

- All prior SOF-VD-09 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
