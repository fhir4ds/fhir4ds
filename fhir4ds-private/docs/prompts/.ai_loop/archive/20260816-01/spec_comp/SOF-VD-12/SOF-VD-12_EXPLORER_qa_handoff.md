# QA Handoff — SOF-VD-12 / EXPLORER (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-12 — Profiling, Shareable/Tabular, Mappings, XML/JSON.
**Spec**: EXPLORER pathological-input probe of profile/metadata boundaries.
**Personality**: EXPLORER (Fuzzer / Abuser).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-12_EXPLORER/probe.py`
**Result**: **PASS — 11/12 probes passed; 1 hypothesis error (INTENDED); 0 real issues.**

## Pathological Inputs Tested

- **E1** Shareable with unicode url (http://éxample.com/.../日本) — PASS.
- **E2** 100 profile declarations — PASS.
- **E3** extremely long canonical url (10000 chars) — PASS.
- **E4** meta.profile null rejected — PASS.
- **E5** meta.profile non-string element rejected — PASS.
- **E6** duplicate Shareable profile declarations — PASS.
- **E7** Tabular accepts all primitive types — initial FAIL.
  Investigated: my test included `date`, which is NOT in the Tabular
  primitive allowlist (`TABULAR_PRIMITIVE_TYPE_NAMES` = 18 primitives
  including dateTime but NOT `date` alone). The implementation correctly
  rejects `date` for Tabular with
  `"TabularViewDefinition column 'v' must declare one of the profile's
  primitive column types"`. My hypothesis was wrong — I should have only
  used Tabular-allowed primitives. The implementation is correct.
- **E8** unsupported mapping variants ignored — PASS.
- **E9** XML string rejected with typed error — PASS.
- **E10** metadata does not change execution result — PASS.
- **E11** Shareable collection column still requires type — PASS.
- **E12** JSON round-trip all optional fields — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-12_EXPLORER/probe.py`

## Notes

- All prior SOF-VD-12 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
