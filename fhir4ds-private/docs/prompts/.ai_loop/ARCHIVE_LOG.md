
## hotfix/qa002-mixed-data-crash (2026-10-13, opencode-fix4)

- 2026-10-13T00:15:00-05:00 WORKTREE_READY (hotfix from dev cf66ab1d; conductor dispatch c-qa002)
- FIX QA-002 (HIGH): kernel.py _build_connection now groups dataset paths by suffix into SEPARATE DatasetSpec/load_dataset calls (ndjson batch + bundle batch; valuesets ride the first spec exactly once; valuesets-only specs still work). Mixed .ndjson + .json workspaces boot; MADiE-import shapes unblocked. Uppercase suffixes route identically.
- FIX QA-004 (MEDIUM): dataset_ops.load_dataset stages each spec inside BEGIN TRANSACTION/COMMIT with ROLLBACK on failure — multi-file datasets are atomic per spec; a later file's strict-load failure no longer leaves earlier files' rows committed. Kernel rebuilds a clean connection on load failure (never serves partial data; diagnostics carry the reason).
- Tests: fhir4ds/devserver/tests/test_kernel_datasets.py (7) — mixed boot+load, homogeneous, uppercase, valuesets-only, multi-file rollback, kernel clean-conn rebuild, successful multi-file commit. E2E: web/dev-server/tests/e2e/mixeddata.spec.ts — mixed workspace boots, /health ok, /api/dataset-stats counts both kinds (>=2 patients).
- 2026-10-13T00:55:00-05:00 GATES: devserver pytest 211/211 (204 baseline + 7 new); operations 186 passed/3 skipped; loader unit 91 + loader/ 220; dev-server e2e 49/49 FIRST PASS (17 spec PYTHONPATHs retargeted to hotfix worktree).
- VERDICT: COMPLETE. Branch left for human merge (never self-merge).
