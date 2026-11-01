# Code Review — v0.0.20 campaign (dev @ 0cb915de15b)

Scope: the unreviewed delta since 0.0.19 (d24e9fc4). Branches that arrived via
merge carried their own review: phase2-opt (independent Qwen3.8-Max review,
67c52da), serve-layer (author's seven review findings with failing-first
tests, 8137acd), vd-form-editor (Joel-reviewed, incl. 282d2f0/a109713 fix
commits), docs-matrix (docs-only). Reviewed here: ext-1.5.6 (e0783fd),
consolidation test-adaptation (80fef08), pin revert (0fb26fa), medterm pin
(cfa5167), D12 provenance pin (0cb915d), QA state/probes.

## Findings: none blocking. CLEAN_WITH_NOTES.

## Verified

1. **Security**: no secrets/credentials in the campaign diff (grep over
   loader/terminology/extension changes: clean). Loader paths are still
   quoted/staged through the existing content-keyed cache — no new injection
   surface (dispatch table is a static dict keyed on parsed version ints).
2. **Loader dispatch edge matrix** (mocked duckdb.__version__): 1.5.5→v155
   bundle, 1.5.6→156 bundle, 1.5.0/1.5.7→v155 bundle (attempted, warns on
   ABI mismatch → documented fallback), 2.0.0→v2 bundle, 2.1.0/1.6.0→None
   (fallback). All as designed.
3. **Staging rename**: `.duckdb2_extension`, `.duckdb156_extension`, and
   plain `.duckdb_extension` all stage to the loadable name correctly.
4. **Binary freshness**: both `.duckdb156_extension` bundles are newer than
   the newest extension source file (built after the final source edit);
   md5s recorded in the commit message; 2870/2870 conformance passed on the
   1.5.6 leg built from exactly this tree.
5. **C++ port (e0783fd)**: cql_extension.cpp diff is large (924 lines) but
   dominated by the 200+ mechanical `ToUnifiedFormat(count, …)` rewrites;
   behavior verified by the full D1/D2 tri-engine probe batteries and
   2870-conformance on the 1.5.6 leg, not by inspection alone. The
   `std::shared_mutex` pthread shim only compiles under pre-C++17 (flag-
   ordering hazard documented in-source); phase-2 shared-read semantics
   preserved (symbol `g_valueset_cache_mutex` present in all three ABIs).
6. **D12 provenance pin** (`prefer_terminology_layout`): import-free by
   construction (fresh-process test proves no medterm4ds import), operator
   `MEDTERM4DS_LAYOUT` wins, foreign-repo manifests ignored, no-release
   environments keep `auto`. NOTE (accepted): when the release is cached the
   pin is sticky for the process even if the subsequent medterm4ds import
   fails — harmless (nothing consumes the layout until a later import
   succeeds) and matches the operator-pin semantics.
7. **Atomicity contract**: extended to 1.5.6 bundles (pin allows 1.5.6 ⇒
   bundles exist); verified on all three duckdb legs.
8. **Ruff**: all new campaign files clean; the 28 findings in serve-layer
   files are pre-existing repo style profile (reported to conductor, not
   fixed per no-extra-commits).

## Notes for the ledger

- The 1.5.6 patch-level ABI lock means every future 1.5.x bump needs a new
  bundle + dispatch entry (or it falls back with a warning). This is the
  documented cost of the dual-bundle decision; the atomicity test now guards
  the dangerous direction.
- `wasm_surface_harness` and `test_fp18_math_operators` load BUILD-TREE
  binaries by path; any future in-tree rebuild for a different ABI must
  restore the shipped-ABI binaries at those paths (this campaign's incident
  is the precedent; follow-up recommendation filed with the conductor to
  make the harness version-aware).
