# QA Handoff — SOF-VD-09 EXPLORER (2026-08-23, iteration 1)

Chunk: SQL-on-FHIR v2 root `ViewDefinition.where`. Personality: EXPLORER
(boundary/fuzz probing per launch mandate).

Spec grounding: SD 2.0.0 (releases/ig/2.0.0
StructureDefinition-ViewDefinition.json — where 0..* root-only, path 1..1,
description 0..1) plus FHIRPath boolean semantics for filter evaluation
(non-singleton-true collections are not true).

Probe: `/mnt/d/fhir4ds/.temp/qa/sof_vd09_explorer_2026_08_23/probe.py` —
23 assertions on native C++ extension and forced Python fallback, plus a
follow-up multi-boolean semantics check. 23/23 PASS, native==fallback on
every execution case.

Boundaries probed (all conformant):
- E1: 56 root wheres (50+ AND-chained) → single flat WHERE with "\n  AND "
  joins, correct filtering, both engines.
- E2: heavy FHIRPath where: nested `where($this=...)`/`exists()`/`iif` tree
  with date arithmetic (`birthDate + 10 years > @2000-01-01`) — correct rows.
- E3/E3b/E3c: HISTORIAN's prefix-mixed-focus guard holds at forEach depth,
  inside unionAll branches, and under a forEach→forEachOrNull→forEach stack —
  all fail loud with the typed ValidationError on both orderings.
- E4: where against absent fields (boolean/string/date comparisons, `not()`,
  `!=`) and JSON-typed-null fields — all exclude, both engines.
- E5: root where + `repeat` view — root filter applied; filtered resource's
  repeat rows absent. (repeat takes the array form.)
- E6: collection-returning where paths — `exists()` true includes; literal
  multi-boolean collections `{true,true}` and `{true,false}` (via
  `name.select(...)`) exclude the row on BOTH engines — matches FHIRPath
  boolean semantics (only singleton true is true) and the established
  non-boolean exclusion doctrine.
- E7: description round-trip with unicode + markdown + 5KB string preserved
  exactly via parse→to_dict; view still executes.
- E8: root where (2 wheres) on a resourceType-mixed shared source table at
  400 rows (200 Patients + 200 Observations) — exact expected set on both
  engines, resourceType guard composed as first AND condition. (Initial
  apparent failure was a probe expectation bug — P maps odd i→female.)
- E9: non-boolean where results (numeric literal `1`, string `'yes'`,
  collection of strings `gender`) — all exclude.
- E10: where referencing a named constant (`gender = %fem`) — correct.
- E11: unknown builtin `%bogus.x` — loud typed failure.

Issues found: NONE. Zero CRITICAL/HIGH/MEDIUM/LOW issues logged.

Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds):
- viewdef pytest: 1227/1227
- ViewDefinition conformance: 144/144 (where.json 8/8)
- Master gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47)
- fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a identical
  across repo bundle and ~/.local site-packages (no native changes this launch).

QA verdict: iteration >= min_iterations(1), zero open issues → clean exit
eligible after FIX (no-op) and ARCHITECT phases.
