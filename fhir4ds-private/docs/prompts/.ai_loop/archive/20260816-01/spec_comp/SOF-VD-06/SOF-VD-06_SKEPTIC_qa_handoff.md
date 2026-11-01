# QA Handoff — SOF-VD-06 / SKEPTIC (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-06 — SQL-on-FHIR ViewDefinition.select.forEach / forEachOrNull.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). `forEach` 0..1 multiplies rows per collection item and suppresses
rows when the collection is empty. `forEachOrNull` 0..1 preserves one null row
when the collection is empty (parent columns from sibling selects keep their
values; columns inside the forEachOrNull select become NULL). Built-in
`%context`/`%resource`/`%rootResource`/`%rowIndex` resolve correctly inside
iterated contexts. `forEach`/`forEachOrNull`/`repeat` are mutually exclusive
(`sql-expressions` constraint).
**Personality**: SKEPTIC (Hypothesis Attacker).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-06_SKEPTIC/probe.py`
**Result**: **PASS — 9/10 assertions; 0 bugs. 1 informational INTENDED finding.**

## Hypotheses Tested

- **H1** forEach multiplies rows per collection item (2 names → 2 rows) — PASS.
- **H2** forEach suppresses rows when collection empty (no name → 0 rows) — PASS.
- **H3** forEachOrNull preserves null row for empty collection — initially
  surfaced a difference (column `id` placed INSIDE the forEachOrNull select
  returned NULL), but verified against the official spec_test fixtures
  (`foreach.json` → "forEachOrNull: null case" and "forEachOrNull: basic")
  that the official pattern uses a SIBLING select for parent columns. Tested
  the sibling-select pattern and confirmed `id` is preserved and the
  forEachOrNull-internal `value` column is NULL. The "row produced will have
  null values" spec language covers columns INSIDE the forEachOrNull select
  stanza. **Classified INTENDED** — matches project AGENTS.md interpretation.
- **H4** nested column evaluated relative to iterated item (`given.first()`) — PASS.
- **H5** forEach + forEachOrNull mutually exclusive — PASS.
- **H6** forEach + repeat mutually exclusive — PASS.
- **H7** present-null forEach rejected — PASS.
- **H8** present-null forEachOrNull rejected — PASS.
- **H9** %rowIndex embedded in iterator column resolves (0,1 ordering) — PASS.
- **H10** sibling column + forEach Cartesian composition (1×2 = 2 rows, pid preserved) — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-06_SKEPTIC/probe.py`

## Notes

- All prior SOF-VD-06 fixes intact: present-null iterator rejection, mutual
  exclusion, %rowIndex substitution, %resource/%rootResource root routing.
- Verified against official `foreach.json` "forEachOrNull: null case" and
  "forEachOrNull: basic" patterns which use sibling selects for parent
  columns. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
