# QA Handoff — SOF-VD-08 / HISTORIAN (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-08 — SQL-on-FHIR ViewDefinition.select.unionAll.
**Spec**: Systematic spec walkthrough against OFFICIAL
`fhir4ds/viewdef/tests/spec_tests/union.json` (10 cases).
**Personality**: HISTORIAN (Spec Compliance Verifier).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-08_HISTORIAN/probe.py`
**Result**: **PASS — 10/10 official spec_tests pass (multiset comparison); 0 issues.**

## Official spec_tests Verified (union.json)

- basic — PASS
- unionAll + column — PASS
- duplicates — PASS (UNION ALL preserves duplicates)
- empty results — PASS
- empty with forEachOrNull — PASS
- forEachOrNull and forEach — PASS
- nested — PASS
- one empty operand — PASS
- column mismatch — PASS (OK_EXPECTED_ERROR)
- column order mismatch — PASS (OK_EXPECTED_ERROR)

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-08_HISTORIAN/probe.py`

## Notes

- All prior SOF-VD-08 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
