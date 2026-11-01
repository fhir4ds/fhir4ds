# QA Handoff — SOF-VD-10 / SKEPTIC (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-10 — Terminology Bindings, Constraints (`sql-name`,
`sql-expressions`), Cardinality.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). `sql-name` regex `^[A-Za-z][A-Za-z0-9_]*$` enforced on
`name`, `constant.name`, `column.name`; `sql-expressions` constraint
forbids combining `forEach`/`forEachOrNull`/`repeat`; required fields
(`resource`, `select`, `column.path`, `column.name`, `constant.name`,
`constant.value[x]`, `where.path`) enforced; `resource` validated against
FHIR ResourceType; `fhirVersion` validated against FHIRVersion.
**Personality**: SKEPTIC (Hypothesis Attacker).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-10_SKEPTIC/probe.py`
**Result**: **PASS — 16/16 hypotheses; 0 issues.**

## Hypotheses Tested (all rejected)

- **H1-H4** sql-name rejects `_bad`, `bad-name`, `bad.name`, `1bad` — PASS.
- **H5** sql-name accepts valid names (id, patient_id, col1, A, CamelCase, a1b2) — PASS.
- **H6** `sql-expressions` rejects forEach + repeat — PASS.
- **H7** missing resource rejected — PASS.
- **H8** missing select rejected — PASS.
- **H9** missing column.path rejected — PASS.
- **H10** missing column.name rejected — PASS.
- **H11** missing constant.name rejected — PASS.
- **H12** missing constant.value[x] rejected — PASS.
- **H13** invalid ResourceType rejected — PASS.
- **H14** invalid fhirVersion rejected — PASS.
- **H15** where.path required — PASS.
- **H16** valid constant sql-name accepted — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-10_SKEPTIC/probe.py`

## Notes

- All prior SOF-VD-10 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
