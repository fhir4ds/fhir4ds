# Architect Handoff — SOF-VD-08 (select.unionAll), iteration 1

## Golden-standard invariants used (focused scope: unionAll generation)
1. Row multiplicity must follow Process(S,N) exactly: parts (columns, each nested select, the unionAll row-set) combine by Cartesian product; unionAll appends branch rows (UNION ALL, duplicates preserved).
2. forEachOrNull empty foci emits exactly ONE null row per selection structure (step 3) — not one per union branch, and never suppressed for structures outside the union expansion.
3. Branch schemas must match in names, FHIR types, collection flags, and order (models.fsh invariant, stricter than official fixtures).
4. Validation happens at parse (structure) and generate (schema) time with typed errors; no silent fallbacks.
5. Generated SQL correctness must be engine-independent (pure SQL shape; both fhirpath engines consume it identically).

## Audit result
- Fix QA-001 (HIGH, RESOLVED) satisfies invariants 1/2: suppression identity moved from path string to union-expansion wrapper instance (`_union_origin_id` marker, preserved through `copy.copy`). No hardcoding, minimal footprint, general to the class (any sibling count, any path collision, nested unions).
- `_generate_multi_resource_union` delegates to `_generate_single_resource` per resource type with a fresh suppression scope per call — correct (each resource processed independently).
- LOW observation (not fixed, scope discipline): `_hoist_nested_unions` and `_build_union_all_query` in generator.py are dead code (only self-recursive references; live path is `_expand_select_unions`). Candidate for deletion in a dedicated cleanup launch.

## QA Enforcer Gate
QA was NOT lazy: mandate checklist fully covered (duplicate preservation, missing-column/order/type rejection, empty array, single branch, nested recursion, forEach/forEachOrNull/repeat combos at multiple levels, where scopes, %rowIndex per branch, columns-only vs generator branches, native/fallback parity confirmation). One real HIGH found and fixed; several initial "expected" values self-corrected against Process(S,N) before logging. No veto — RETRY_QA stays false.

## Empirical validation (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- viewdef pytest: 1196/1196 (3 new regression tests).
- ViewDefinition conformance: 144/144. Master gate run_all.py: 2832/2832 first pass.
- fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a, repo == site-packages (no rebuild).

## State
1 issue total: QA-001 HIGH RESOLVED (tombstoned; details in ARCHIVE_LOG.md). Zero non-terminal issues. Iteration 1 >= min_iterations 1 -> clean exit recommended.
