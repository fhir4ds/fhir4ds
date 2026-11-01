# QA Handoff — SOF-VD-08 / SKEPTIC (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-08 — SQL-on-FHIR ViewDefinition.select.unionAll.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). `unionAll` 0..* concatenates branch rowsets preserving all
duplicates (UNION ALL, not UNION). Branch schemas must match by name/order/
type/collection. Branch-local `where` stays branch-scoped. Nested unionAll
recurses. Present-empty/null arrays rejected.
**Personality**: SKEPTIC (Hypothesis Attacker).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-08_SKEPTIC/probe.py`
**Result**: **PASS — 10/10 hypotheses; 0 issues.**

## Hypotheses Tested (all rejected)

- **H1** unionAll combines branch rows (telecom + contact.telecom → 3) — PASS.
- **H2** unionAll preserves duplicate rows (UNION ALL semantics) — PASS.
- **H3** branch column-count mismatch rejected — PASS.
- **H4** present-empty `unionAll: []` rejected — PASS.
- **H5** present-null unionAll rejected — PASS.
- **H6** nested unionAll recursion (unionAll inside branch) — PASS.
- **H7** unionAll branch with forEachOrNull null-row preservation — PASS.
- **H8** branch-local where scoped to branch — PASS.
- **H9** branch type mismatch rejected — PASS.
- **H10** sibling unionAll groups compose via Cartesian — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-08_SKEPTIC/probe.py`

## Notes

- All prior SOF-VD-08 fixes intact (SKEPTIC/HISTORIAN/EXPLORER 2026-05-20
  and 2026-06-01 fresh reruns). No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
