# RELEASE PREP — v0.0.18 (post-S32)

## WASM rebuild + retest

- The WASM extension was rebuilt **after** the final C++ change:
  `extensions/cql/build/wasm_eh/.../cql.duckdb_extension.wasm` md5
  `5bc222aa060a68495d44ac89c0dd4672`, copied to `web/cql-cleanroom/public`,
  `web/wasm-demo/public`, and both deployed static targets.
- End-to-end retest on the final artifacts (wheel `cdcaacf2`,
  ext `5bc222aa`): standalone `cms125-workspace` boots into DuckDB-WASM, cells
  split (17), **Run All executes with no Catalog/Binder errors**, footer shows
  0.0.18. Browser-equivalent function coverage: 69 three-way harness cases
  (`fhir4ds/operations/tests/test_wasm_surface_parity.py`).

## Branch integration — merge, not rebase

- Branch was 27 behind / 139 ahead of `origin/main` (diverged). Rebasing would
  rewrite 139 published commits and require a force-push, which the standing
  rules prohibit without explicit approval.
- **Merged `origin/main`** (`6cdf8dc0`). Only the four `docs/notebooks/*.ipynb`
  overlapped; conflicts resolved by taking main's E2E-validated versions,
  bumping 0.0.17 → 0.0.18, and re-executing all four against the local 0.0.18
  wheel (`PIP_FIND_LINKS=dist`). All four execute with zero error outputs.
- `web/viewing-room/` (new on main) merged cleanly.
- Recommendation: squash-merge the PR if linear `main` history is required.

## Benchmarks

See `benchmarks_s32.md`: 47 measures, **100% accuracy**, total 60.9s → 86.7s
(1.42x, single run on a loaded WSL host), median per-measure 1.12x, 16 measures
>1.25x. SQL-size median 1.006x. The drift is consistent with the documented
correctness-surface growth; rerun on an idle host for a tighter comparison.

## Gates after merge

- Post-merge conformance: see `/tmp/opencode/conformance_merge.log` (expected
  2832/2832; appended by the orchestrator).
- Notebooks 4/4 executed clean (0 error cells, 0.0.18 referenced).
- Prior gates (pre-merge, same code): conformance 2832/2832, cql 3194 passed,
  other pytest 4046 passed (2 pre-existing FHIRPath parity gaps), vitest 197,
  clean-venv smoke clean.
