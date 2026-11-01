# QA Handoff — SOF-VD-06 / EXPLORER (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-06 — SQL-on-FHIR ViewDefinition.select.forEach / forEachOrNull.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). EXPLORER chaos/pathological-input probe of iterator boundaries.
**Personality**: EXPLORER (Fuzzer / Abuser).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-06_EXPLORER/probe.py`
**Result**: **PASS — 10/10 pathological-input probes pass; 0 issues.**

## Pathological Inputs Tested

- **E1** forEach nested 100-deep (contact → telecom) produces 100 rows — PASS.
- **E2** forEachOrNull + nested forEach null case (0-1 rows) — PASS.
- **E3** forEach over single-value boolean produces 1 row — PASS.
- **E4** forEach with where filters iterated rows (1 row after filter) — PASS.
- **E5** malformed forEach FHIRPath rejected — PASS.
- **E6** forEach over unicode/emoji family values — PASS.
- **E7** forEach over 1000-element array (performance) — PASS.
- **E8** forEach with `collection=true` column projects array — PASS.
- **E9** forEachOrNull over empty array preserves null row — PASS.
- **E10** forEach over null field suppresses rows — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-06_EXPLORER/probe.py`

## Notes

- All earlier SOF-VD-06 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
