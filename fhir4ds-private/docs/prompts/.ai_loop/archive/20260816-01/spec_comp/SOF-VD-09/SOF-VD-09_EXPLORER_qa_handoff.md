# QA Handoff — SOF-VD-09 / EXPLORER (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-09 — SQL-on-FHIR Where.
**Spec**: EXPLORER pathological-input probe of where boundaries.
**Personality**: EXPLORER (Fuzzer / Abuser).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-09_EXPLORER/probe.py`
**Result**: **PASS — 12/12 pathological probes pass; 0 issues.**

## Pathological Inputs Tested

- **E1** where with unicode comparison (日本語) — PASS.
- **E2** where with deeply nested FHIRPath (10 levels) — PASS.
- **E3** 50 where clauses (all must be true) — PASS.
- **E4** malformed where FHIRPath rejected — PASS.
- **E5** empty where.path rejected — PASS.
- **E6** whitespace-only where.path rejected — PASS.
- **E7** where.description with markdown (multi-line) — PASS.
- **E8** present-null where.description rejected — PASS.
- **E9** non-string where.description rejected — PASS.
- **E10** where with `iif` complex boolean logic — PASS.
- **E11** where with collection-valued boolean result — PASS.
- **E12** where preserves root scope through `forEach` — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-09_EXPLORER/probe.py`

## Notes

- All prior SOF-VD-09 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
