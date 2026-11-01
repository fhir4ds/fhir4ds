# QA Handoff — SOF-VD-11 / HISTORIAN (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-11 — View Runner, Examples.
**Spec**: Systematic spec walkthrough across 6 OFFICIAL spec_test files
(basic, view_resource, fn_reference_keys, fn_boundary, row_index, combinations).
**Personality**: HISTORIAN (Spec Compliance Verifier).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-11_HISTORIAN/probe.py`
**Result**: **PASS — 38/40 official spec_tests pass; 2 INTENDED normalization artifacts; 0 real issues.**

## Official spec_tests Verified

- **basic.json**: 11/11 PASS
- **view_resource.json**: 3/3 PASS
- **fn_reference_keys.json**: 3/3 PASS
- **fn_boundary.json**: 6/8 PASS (2 INTENDED normalization artifacts — see below)
- **row_index.json**: 9/9 PASS
- **combinations.json**: 6/6 PASS

## INTENDED Findings (fn_boundary decimal lowBoundary/highBoundary)

The 2 "failures" (`decimal lowBoundary`, `decimal highBoundary`) are
**test-harness normalization artifacts**, NOT implementation bugs:
- Expected: `{id: o2, decimal: None}` (Python None)
- Actual: `{id: o2, decimal: NaN}` (pandas float NaN)

Both represent the same semantics: o2/o3/o4 have no `valueQuantity`, so
the `lowBoundary()`/`highBoundary()` result is absent. DuckDB represents
SQL NULL for DOUBLE columns as `float('nan')` in pandas, while the
spec_test fixture encodes it as JSON `null` → Python `None`. The actual
boundary VALUES are correct (0.95, 1.05 for o1). The datetime/date/time
boundary cases all pass exactly (string-typed columns don't have this
artifact). Per AGENTS.md SOF-VD-04 EXPLORER 2026-06-01, boundary
functions are in the compatibility set.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-11_HISTORIAN/probe.py`

## Notes

- All prior SOF-VD-11 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
