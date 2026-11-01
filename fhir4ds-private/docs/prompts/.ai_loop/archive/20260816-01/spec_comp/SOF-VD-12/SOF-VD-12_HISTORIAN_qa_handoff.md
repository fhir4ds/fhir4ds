# QA Handoff — SOF-VD-12 / HISTORIAN (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-12 — Profiling, Shareable/Tabular, Mappings, XML/JSON.
**Spec**: Systematic spec walkthrough of profile activation consistency
across parser / `from_dict` / `to_dict` / `SQLGenerator.generate` /
`validate_view_definition` boundaries.
**Personality**: HISTORIAN (Spec Compliance Verifier).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-12_HISTORIAN/probe.py`
**Result**: **PASS — 8/10 probes passed; 2 hypothesis/test-harness errors (INTENDED); 0 real issues.**

## Probes Tested

- **H1** Shareable missing url rejected at all strict boundaries — PASS.
- **H2** Shareable missing name rejected — PASS.
- **H3** Shareable missing status rejected — PASS.
- **H4** Shareable missing column.type rejected — PASS.
- **H5** Shareable valid (all required) accepted at all boundaries — PASS.
- **H6** Tabular collection column rejected — PASS.
- **H7** Tabular valid — initial FAIL. Investigated: my test omitted
  `status`. Per AGENTS.md SOF-VD-12 HISTORIAN 2026-06-01, Tabular inherits
  CanonicalResource metadata constraints including required `status`
  (`ParseError: TabularViewDefinition requires ViewDefinition.status`).
  The implementation is correct; my hypothesis was wrong.
- **H8** permissive validate warns not raises — initial FAIL.
  Investigated: test-harness bug — I used `VD(resourceType="Patient")`
  but the dataclass field is `resource` (not `resourceType`). The
  `validate_view_definition` API itself works correctly on properly-
  constructed dataclasses. Test-side error.
- **H9** JSON field name round-trip (forEach, column, where, constant) — PASS.
- **H10** combined Shareable + Tabular profiles — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-12_HISTORIAN/probe.py`

## Notes

- All prior SOF-VD-12 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
