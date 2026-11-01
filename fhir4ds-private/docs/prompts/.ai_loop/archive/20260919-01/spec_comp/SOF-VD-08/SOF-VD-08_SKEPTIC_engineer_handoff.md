# Engineer Handoff — SOF-VD-08, iteration 1

## Triage
| Issue | Category | Severity | Triage | Terminal |
|---|---|---|---|---|
| QA-001 | SPEC_VIOLATION (Process(S,N) step 3 + step 2.5) | HIGH | CONFIRMED (reproducers p2.py P1b/P2) | RESOLVED |

## QA-001 fix
- File: /mnt/d/fhir4ds/fhir4ds/viewdef/generator.py
- Root cause: `_generate_single_resource` keyed null-row suppression by resolved forEachOrNull PATH across UNION ALL alternatives, so an independent sibling select repeating a wrapper's path had its spec-mandated null row suppressed in later alternatives (row loss; total row loss in the wrapper+same-path-sibling variant).
- Fix (minimal, general): `_expand_select_unions` tags each replicated wrapper with `_union_origin_id = id(union-owning select)`; `copy.copy` in `_copy_select_for_union_expansion` preserves the marker; `_collect_union_wrapper_ids` replaces `_collect_foreachornull_paths`; suppression now applies only to wrapper copies already seen, siblings never.
- Spec: Process(S,N) step 3 — forEachOrNull empty foci emits exactly one null row per selection structure; step 2.5 — parts (each S.select) cross-join independently.
- Regression: fhir4ds/viewdef/tests/unit/test_union.py::TestUnionAllForEachOrNullSuppression (3 tests: sibling null row kept; wrapper+same-path sibling single cross-joined null row; wrapper-alone single null row pin).
- No native/binary change (pure Python SQL-shape logic; divergence was engine-independent, fix is too). fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a unchanged, repo==site-packages.

## Validation (fresh, final tree)
- viewdef pytest: 1196 passed (1193 baseline + 3 new).
- ViewDefinition conformance: 144/144.
- Master gate run_all.py: 2832/2832 (FHIRPath 935, CQL 1706, DQM 47) — first pass, no ERROR retries needed.

## New issues discovered
None.
