# QA Handoff — SOF-VD-10 / EXPLORER (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-10 — Terminology Bindings, Constraints, Cardinality.
**Spec**: EXPLORER pathological-input probe of constraint boundaries.
**Personality**: EXPLORER (Fuzzer / Abuser).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-10_EXPLORER/probe.py`
**Result**: **PASS — 16/16 pathological probes pass; 0 issues.**

## Pathological Inputs Tested

- **E1** sql-name rejects 12 special characters (!, @, #, $, %, &, *, (, ), +, =, ?) — PASS.
- **E2** sql-name rejects unicode column names (日本語) — PASS.
- **E3** extremely long valid sql-name (1001 chars) accepted — PASS.
- **E4** all 3 iterators together rejected — PASS.
- **E5** forEachOrNull + repeat rejected — PASS.
- **E6** resource as array rejected — PASS.
- **E7** resource as null rejected — PASS.
- **E8** select as null rejected — PASS.
- **E9** empty select array rejected — PASS.
- **E10** column as object (not array) rejected — PASS.
- **E11** multiple value[x] fields on constant rejected — PASS.
- **E12** unsupported valueCoding rejected — PASS.
- **E13** fhirVersion as string (not array) rejected — PASS.
- **E14** profile canonical with whitespace rejected — PASS.
- **E15** direct Constant dataclass validates name via __post_init__ — PASS.
- **E16** direct Column dataclass validates name via __post_init__ — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-10_EXPLORER/probe.py`

## Notes

- All prior SOF-VD-10 fixes intact (incl. dataclass __post_init__ validators
  from SOF-VD-02/03 SKEPTIC 2026-07-03). No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
