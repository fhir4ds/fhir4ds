# QA Handoff — SOF-VD-05 / HISTORIAN (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-05 — SQL-on-FHIR v2 `ViewDefinition.select.select` (Nested
select contentReference).
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). Authoritative normative sources cited per-test below.
**Personality**: HISTORIAN (Spec Compliance Verifier — systematic section-by-section).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd05_historian_2026_07_03_fresh/probe.py`
**Result**: **PASS — 13/13 assertions across all 6 chunk items; 0 issues.**

## Spec-section-by-section verification

| Test | Chunk Item | Normative spec citation | Result |
|---|---|---|---|
| I1 three-level-recursion | I1 recursion cardinality | `ValidateColumns` step 3 + Column Ordering section ("parent select's columns before the columns of the nested `select`") | PASS — cols `[a, b, c]` |
| I2 child-uses-parent-forEach | I2 child uses parent forEach | "forEach ... apply both to the columns within a `select` and any nested `select`s it contains" | PASS — row `(Smith, John)` |
| I2b forEachOrNull-null-row-child-null | I2 child uses parent forEachOrNull | Process step 3 null-row binding + forEachOrNull description | PASS — row `(NULL, NULL)` |
| I3 default-context-this | I3 default `$this` context | Process step 1 "Otherwise: `[N]` (a list with just the input node)" | PASS — row `(p1, 'true')` |
| I4 parent-child-sibling-cartesian | I4 parent+child combine | Multiple Select Expressions: "Parent/child `select`s will repeat values from the parent `select` for each item in the child `select`. Sibling `select`s are effectively cross joined" | PASS — 2 Cartesian rows |
| I5 duplicate-name (3 cases × 2 boundaries) | I5 duplicate-name validation | `ValidateColumns` step 3 "If a Column with name `c.name` already exists in `Ret`, throw Column Already Defined" | PASS — all 6 reject |
| I6a empty-nested-select-no-op | I6 empty combinations | `ValidateColumns` step 3 returns `Ret` unchanged for empty `select[]`; Process step 2.3 contributes no rows | PASS — row `(p1,)` |
| I6b select-only-nested-no-direct-column | I6 empty combinations | `ValidateColumns` step 2 (no cols) + step 3 (recurse into nested) | PASS — row `(p1,)` |

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd05_historian_2026_07_03_fresh/probe.py`

## Notes

- All 6 chunk items verified end-to-end across parser, `ViewDefinition.from_dict`,
  direct dataclass `SQLGenerator.generate`, and DuckDB execution.
- Behavioral confirmation: when a column has no declared `type` and the FHIRPath
  result is a JSON boolean, the generator emits the value serialized as the
  string token `'true'`/`'false'`. This is consistent with the spec's note that
  "It is reasonable for an implementation to treat any non-specified types as
  strings." NOT A BUG.
- All earlier SOF-VD-05 SKEPTIC/EXPLORER/HISTORIAN findings remain intact
  (recursive `Select.to_dict()` where validation, recursive unionAll hoisting,
  parent-context inheritance for child iterators).
