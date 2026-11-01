# QA Handoff — SOF-VD-08 / EXPLORER (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-08 — SQL-on-FHIR ViewDefinition.select.unionAll.
**Spec**: EXPLORER pathological-input probe of unionAll boundaries.
**Personality**: EXPLORER (Fuzzer / Abuser).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-08_EXPLORER/probe.py`
**Result**: **PASS — 9/10 probes passed; 1 DEFERRED observation (low-severity, spec-silent); 0 open issues.**

## Pathological Inputs Tested

- **E1** unionAll with 100 branches — PASS.
- **E2** deeply nested unionAll (5 levels) — PASS.
- **E3** unionAll with one empty branch — PASS.
- **E4** unionAll branch with `collection=true` column — PASS.
- **E5** unionAll matching branch types — PASS.
- **E6** unionAll with unicode/emoji values (日本語, 🄰🄱🄲) — PASS.
- **E7** non-object unionAll member rejected — PASS.
- **E8** unionAll with repeat branches — PASS.
- **E9** branch where filters do not leak across branches — PASS.
- **E10** branch with no rowset producer (where-only) — DEFERRED.
  Investigated: a `unionAll` branch with only `where` and no
  `column`/`select`/`forEach`/`unionAll`/`repeat` does NOT raise —
  instead it generates `SELECT NULL WHERE FALSE` (0 rows, benign no-op).
  The spec does not explicitly require each unionAll branch to contain a
  rowset producer, and the resulting SQL is harmless. Classified DEFERRED
  per Remediation Engineer rules (spec-silent, low-severity, no wrong
  data produced). QA-001 logged for tracking.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-08_EXPLORER/probe.py`

## Notes

- All prior SOF-VD-08 fixes intact. No source changes required for
  clean behavior. QA-001 is DEFERRED (terminal, does not block chunk).
- ViewDefinition pytest 1055/1055 PASS.
