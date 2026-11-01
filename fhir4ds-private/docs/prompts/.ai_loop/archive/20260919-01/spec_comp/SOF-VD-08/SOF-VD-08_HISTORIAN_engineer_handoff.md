# Engineer Handoff — SOF-VD-08, HISTORIAN iteration 1

## Triage
| Issue | Category | Severity | Triage | Terminal |
|---|---|---|---|---|
| QA-001 | SPEC_VIOLATION (Process(S,N) step 3) | HIGH | CONFIRMED (probe.py P1/P1b/P2/P4) | RESOLVED |

## QA-001 fix
- File: /mnt/d/fhir4ds/fhir4ds/viewdef/generator.py
- Root cause: null-row suppression across UNION ALL alternatives only recognized `_union_origin_id` wrappers at the top level of the select list (`_collect_union_wrapper_ids`) and `_process_selects` did not recurse alias collection — a forEachOrNull+unionAll wrapper nested under forEach/forEachOrNull/unionAll branches escaped suppression, duplicating its spec-mandated null row in every non-first union branch.
- Fix (minimal): `_process_selects` now takes a paired `foreachornull_wrapper_ids` list, appends the select's `_union_origin_id` (None for non-wrappers) in lockstep with each forEachOrNull alias at the emission site, and recurses BOTH lists into nested selects. `_generate_single_resource` consumes the paired lists directly; `_collect_union_wrapper_ids` deleted. Independent siblings still never suppressed; wrappers suppressed once at any depth.
- Regression tests: fhir4ds/viewdef/tests/unit/test_union.py::TestUnionAllForEachOrNullSuppression — 4 new tests (nested wrapper under forEach single null row per focus; under empty outer forEachOrNull single all-null row; wrappers inside union branches one null row per wrapper instance; populated-foci pin).
- Engine-independent (Python SQL-shape logic; probes ran under the native fhirpath extension). No binary change: fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a, repo==site-packages.

## Validation (fresh, final tree, PYTHONPATH=/mnt/d/fhir4ds)
- viewdef pytest: 1200 passed (1196 baseline + 4 new).
- ViewDefinition conformance: 144/144.
- Master gate run_all.py: 2832/2832 (FHIRPath 935, CQL 1706, DQM 47) — first pass, no retries.

## New issues discovered
None.
