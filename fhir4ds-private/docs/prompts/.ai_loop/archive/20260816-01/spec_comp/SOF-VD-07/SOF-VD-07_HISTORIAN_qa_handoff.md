# QA Handoff — SOF-VD-07 / HISTORIAN (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-07 — SQL-on-FHIR ViewDefinition.select.repeat.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). HISTORIAN systematic spec walkthrough against the OFFICIAL
`fhir4ds/viewdef/tests/spec_tests/repeat.json` fixtures (7 cases).
**Personality**: HISTORIAN (Spec Compliance Verifier).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-07_HISTORIAN/probe.py`
**Result**: **PASS — 7/7 official spec_tests pass (multiset comparison); 0 issues.**

## Official spec_tests Verified (repeat.json)

- basic — PASS
- item and answer.item — PASS
- empty expression — PASS
- empty child expression — PASS
- combined with forEach — PASS
- combined with forEachOrNull — PASS
- combined with unionAll — PASS

## Methodology

Per AGENTS.md (SOF-VD-07 EXPLORER 2026-06-01), SQL row order after repeat
filtering is not a conformance signal. Comparison uses row MULTISETS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-07_HISTORIAN/probe.py`

## Notes

- All prior SOF-VD-07 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
