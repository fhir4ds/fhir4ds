# QA Handoff — SOF-VD-06 / HISTORIAN (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-06 — SQL-on-FHIR ViewDefinition.select.forEach / forEachOrNull.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). HISTORIAN performs a systematic spec walkthrough against the
OFFICIAL `fhir4ds/viewdef/tests/spec_tests/foreach.json` fixtures (13 cases).
**Personality**: HISTORIAN (Spec Compliance Verifier).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-06_HISTORIAN/probe.py`
**Result**: **PASS — 13/13 official spec_tests pass (multiset comparison); 0 issues.**

## Official spec_tests Verified (foreach.json)

- forEach: normal — PASS (4 rows: pt1/F1.1, pt1/F1.2, pt2/F2.1, pt2/F2.2)
- forEachOrNull: basic — PASS (5 rows incl. pt3 null row)
- forEach: empty — PASS (0 rows)
- forEach: two on the same level — PASS (4 rows, Cartesian)
- forEach: two on the same level (empty result) — PASS (0 rows)
- forEachOrNull: null case — PASS (3 rows, value NULL, id preserved)
- forEach and forEachOrNull on the same level — PASS
- nested forEach — PASS (3 rows)
- nested forEach: select & column — PASS
- forEachOrNull & unionAll on the same level — PASS (7 rows)
- forEach & unionAll on the same level — PASS (5 rows)
- forEach & unionAll & column & select on the same level — PASS (5 rows)
- forEachOrNull & unionAll & column & select on the same level — PASS (7 rows)

## Methodology Note

Per AGENTS.md (SOF-VD-07 EXPLORER 2026-06-01): SQL row order after
select-level filtering is not a conformance signal by itself. The probe
therefore compares row MULTISETS (sorted by row-tuple), not physical row
order. All 13 official cases pass as multisets; row counts, keys, and
per-cell values all match the spec-expected output.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-06_HISTORIAN/probe.py`

## Notes

- All earlier SOF-VD-06 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS (verified separately).
