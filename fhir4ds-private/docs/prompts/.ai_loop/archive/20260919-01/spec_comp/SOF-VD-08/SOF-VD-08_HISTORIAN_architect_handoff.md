# Architect Handoff — SOF-VD-08, HISTORIAN iteration 1

## Audit: PASS (RETRY_QA not set)
- Fix correctness: suppression now keyed to wrapper identity at the exact alias-emission site, recursed in lockstep with SQL generation — structurally cannot misalign (the old approach derived ids from a separate top-level-only walk). Independent siblings unaffected (verified by retained SKEPTIC tests).
- Root cause addressed, not shimmed: the divergent parallel bookkeeping (`_collect_union_wrapper_ids`) was deleted, not patched.
- Scope: minimal, single file + tests. No API change; `foreachornull_aliases` recursion semantic widened but sole consumer is the suppression zip.
- Gates: viewdef 1200, ViewDef 144/144, run_all 2832/2832 first pass; binary md5 57d0634b unchanged repo==site-packages.

## Assessment
The SKEPTIC fix was spec-correct but incomplete in scope: it fixed the suppression key (path -> wrapper instance) without auditing the traversal depth of the bookkeeping. The HISTORIAN pass closed the remaining depth dimension. Chunk SOF-VD-08 now triangulated on: duplicate preservation, branch schema rejection, arm model, where scoping, %rowIndex, repeat/forEach/forEachOrNull composition, and null-row suppression at all nesting depths. Clean exit at min_iterations=1 with zero non-terminal CRITICAL/HIGH/MEDIUM issues.

## Doctrinal note
Recurring theme (2nd occurrence): unionAll null-row suppression bugs are fixture-invisible — official union.json never combines forEachOrNull with unionAll wrappers. Any future change to `_expand_select_unions`/`_process_selects` must re-run TestUnionAllForEachOrNullSuppression and reason about wrapper copies at arbitrary depth.
