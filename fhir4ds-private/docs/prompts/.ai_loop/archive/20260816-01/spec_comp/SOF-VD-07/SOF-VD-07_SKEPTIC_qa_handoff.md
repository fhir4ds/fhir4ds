# QA Handoff — SOF-VD-07 / SKEPTIC (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-07 — SQL-on-FHIR ViewDefinition.select.repeat.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). `repeat` 0..* FHIRPath expressions recursively traverse to any
depth; multiple paths combine via union semantics; columns resolve against
each repeated node; mutual exclusion with `forEach`/`forEachOrNull`;
present-empty/null arrays rejected as invalid FHIR JSON shape.
**Personality**: SKEPTIC (Hypothesis Attacker).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-07_SKEPTIC/probe.py`
**Result**: **PASS — 10/10 hypotheses; 0 issues.**

## Hypotheses Tested (all rejected)

- **H1** single repeat path produces all nodes at any depth (5 nodes from nested QR) — PASS.
- **H2** multiple repeat paths unioned (item + item.answer → 5 nodes) — PASS.
- **H3** present-empty `repeat: []` rejected — PASS.
- **H4** repeat + forEach mutually exclusive — PASS.
- **H5** present-null repeat rejected — PASS.
- **H6** columns evaluated against each repeated node (linkId+text) — PASS.
- **H7** `$this.linkId` explicit self-traversal — PASS.
- **H8** `%rowIndex` on repeated nodes (0,1,2) — PASS.
- **H9** scalar string repeat rejected (must be array) — PASS.
- **H10** repeat over absent field produces 0 rows — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-07_SKEPTIC/probe.py`

## Notes

- All prior SOF-VD-07 fixes intact (SKEPTIC/HISTORIAN/EXPLORER 2026-05-20
  and 2026-06-01 fresh reruns). No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
