# QA Handoff — SOF-VD-11 / SKEPTIC (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-11 — View Runner, Examples.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). Runner executes ViewDefinition and returns tabular rows via
`SQLGenerator.generate(vd) -> SQL` + DuckDB execution. Type coercion,
getResourceKey, array unrolling, filters, and shared-table resourceType
isolation all exercised.
**Personality**: SKEPTIC (Hypothesis Attacker).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-11_SKEPTIC/probe.py`
**Result**: **PASS — 10/10 hypotheses; 0 issues.**

## Hypotheses Tested (all rejected)

- **H1** getResourceKey() projection (`Patient/p1`) — PASS.
- **H2** Observation valueQuantity.value decimal projection (42.5) — PASS.
- **H3** Patient.address forEach unrolling (2 cities) — PASS.
- **H4** filtered Observation view (status='final') — PASS.
- **H5** integer column type coercion (42) — PASS.
- **H6** boolean column type coercion (True) — PASS.
- **H7** shared table resourceType filter (Patient isolated from Observation) — PASS.
- **H8** %rowIndex integer column (0,1,2) — PASS.
- **H9** multi-patient isolation (2 patients → 2 rows) — PASS.
- **H10** empty result set (0 rows when no matching resources) — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-11_SKEPTIC/probe.py`

## Notes

- All prior SOF-VD-11 fixes intact (SKEPTIC/HISTORIAN/EXPLORER 2026-05-20
  and 2026-06-01 fresh reruns). No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
