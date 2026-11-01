# QA Handoff — SOF-VD-05 / EXPLORER (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-05 — SQL-on-FHIR v2 `ViewDefinition.select.select` (Nested
select contentReference).
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). Pathological compositions tested against `Process(S, N)` recursive
algorithm (Cartesian-product semantics) and `ValidateColumns` recursion.
**Personality**: EXPLORER (Fuzzer / Abuser).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd05_explorer_2026_07_03_fresh/probe.py`
**Result**: **PASS — 11/11 assertions across 8 pathological batteries; 0 issues.**

## Batteries Tested

| Battery | Pathological input | Spec-citation | Result |
|---|---|---|---|
| E1 deeply-mixed | parent forEach + 2 sibling nested selects + nested unionAll | Process step 2.2/2.3/2.4 Cartesian | PASS — 4 rows `[family,given_first,src]` |
| E2 nested-where-filter | nested select with own `where` clause scoped to parent forEach focus | Process step (where is select-scoped) | PASS — 1 row (Jones branch filtered) |
| E3 forEach-only-nested-entry | nested entry with forEach and column but no further nesting | Process step 1+2 (forEach row generator) | PASS — 2 rows |
| E4 nested-forEach-collection-col | nested forEach over multi-collection target with `collection=true` column | Process step 2.2 collection branch | PASS — 2 rows, lines col is array |
| E5 sibling-iterators-empty | sibling forEachOrNull + forEach in nested selects (empty case) | Process step 3 (null row) + Cartesian | PASS — 0 rows (1×0=0) |
| E5 sibling-iterators-populated | same composition (populated case) | Cartesian | PASS — 2 rows (1×2=2) |
| E6 empty-column-plus-unionall-nested | nested select with empty column[] + unionAll together | ValidateColumns step 4 + Column Ordering | PASS — 2 rows `[id,v,extra]` |
| E7 parity × 3 | parser/from_dict parity for valid / duplicate-name-deep / present-null-nested | parser==from_dict contract | PASS — all 3 match |
| E8 zero-row-cartesian | nested forEach over empty collection yields 0 rows | Process step 2.3 Cartesian with empty set | PASS — 0 rows (cols still defined) |

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd05_explorer_2026_07_03_fresh/probe.py`

## Notes

- All pathological compositions behave per the spec's `Process(S, N)` algorithm.
- E5/E8 confirm the Cartesian-product semantics precisely: empty rowset ×
  anything = empty rowset; null-preserved row from forEachOrNull participates
  in the Cartesian product like any other single-row rowset.
- E7 confirms `parse_view_definition()` and `ViewDefinition.from_dict()`
  produce identical accept/reject decisions across pathological nested inputs,
  preserving the parser/from_dict lockstep contract.
- All earlier SOF-VD-05 fixes remain intact (recursive `Select.to_dict()` where
  validation, recursive unionAll hoisting under default `$this`, parent-context
  inheritance for child iterators).
