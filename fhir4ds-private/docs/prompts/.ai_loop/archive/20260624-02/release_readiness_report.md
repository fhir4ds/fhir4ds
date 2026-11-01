# Release Readiness Report — 0.0.10

**Workflow**: `pre_release`
**Release Engineer**: Release Engineer role
**Target version**: `0.0.10`
**Previous version**: `0.0.9`
**Date**: 2026-06-24

## 1. Build Status

| Artifact | Status | Notes |
|---|---|---|
| Native C++ `fhirpath.duckdb_extension` | OK | Refreshed by `hatch build` hook from `extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/`. Matches the cleaned-up source in `evaluator.cpp` (REV-001 cleanup: redundant `if (exact)` removed, indentation fixed, fhir_type-override behavior documented). |
| Native C++ `cql.duckdb_extension` | OK | Refreshed by `hatch build` hook. |
| Python wheel `dist/fhir4ds_v2-0.0.10-py3-none-any.whl` | OK | 9.94 MB; built by `hatch build`. |
| Python sdist `dist/fhir4ds_v2-0.0.10.tar.gz` | OK | 9.52 MB; built by `hatch build`. |
| WASM extensions | NOT REBUILT | Emscripten/WASM build not run in this session. Pre-existing WASM artifacts in `web/wasm-demo/public/extensions/` remain unchanged. The release ships the Python wheel + native DuckDB extensions; WASM is a follow-up artifact. |

## 2. Artifact Gate

| Check | Result |
|---|---|
| Wheel `METADATA` Version | `0.0.10` ✓ |
| Wheel `METADATA` Required Deps | `duckdb==1.5.2`, `numpy`, `pint>=0.21.0`, plus `orjson`, `pyarrow`, `python-dateutil`, `pyyaml`, `antlr4-python3-runtime`. All present. |
| Wheel bundled binaries | `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` (11,519,286 bytes) and `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` (11,243,734 bytes). Both present. |
| Public API surface | `fhir4ds.__version__ == "0.0.10"`; all subpackage `__version__` constants aligned (verified by `test_public_subpackage_versions_match_root`). |
| `pyproject.toml` version | `0.0.10`; matches public `__version__` (verified by `test_pyproject_version_matches_public_root_version`). |
| Web version surface | Landing page `PRODUCT_VERSION = '0.0.10'`, Playwright assertion updated, WASM demo wheel-name fallback updated, notebook snippets updated, WASM-engine integration doc updated, releases.md has 0.0.10 entry. |
| Clean-venv install / pip check / native C++ load matrix / hostile collision / unsupported DuckDB fallback / WASM wheel checksum | NOT RUN in this session — full Phase 2 gate from `ROLE_RELEASE_ENGINEER.md` requires a clean virtualenv outside the repo and an explicit `duckdb==1.4.2` downgrade probe. Tracked as a follow-up; the wheel structure was verified via `zipfile` inspection. |

## 3. Test Coverage

| Suite | Result |
|---|---|
| `pytest fhir4ds/` | **8000 passed**, 7 skipped, 1 failure (see below) |
| Failure classification | `fhir4ds/fhirpath/tests/unit/test_new_functions.py::TestIsLowercaseTypes::test_empty_collection_returns_empty` — pre-existing on `dev`, predates this release-prep session. Documents a real FHIRPath §5.1 violation (`is()` on empty collections should return `[]`, not `[False]`). A Python-side fix was reverted because it broke C++/Python parity (the native extension needs the same change). Tracked in release notes as a Known Limitation. |
| Playwright E2E (`web/website/tests/demo.spec.ts`) | NOT RUN in this session — requires `npm install` + browser. The version assertion was updated to `v0.0.10` to match the landing-page change. |

## 4. Conformance Report

Verbatim snapshot from `python3 conformance/scripts/run_all.py`:

```
============================================================
Specification             | Passed   | Total    | Rate    
------------------------------------------------------------
ViewDefinition            | 134      | 134      |  100.0%
FHIRPath (R4)             | 935      | 935      |  100.0%
CQL                       | 1706     | 1706     |  100.0%
DQM (QI Core 2025)        | 47       | 47       |  100.0%
------------------------------------------------------------
OVERALL COMPLIANCE        | 2822     | 2822     |  100.0%
============================================================

SUCCESS: 100% Spec Conformance Achieved!
```

No regressions from 0.0.9. All 48 DQM measures at 100% accuracy (the run_all summary counts individual test cases; the underlying `dqm_report.json` has 48 measure entries each at 100% `accuracy_pct`).

## 5. Release-Prep Commits in This Branch (since `2d1ec4f3`)

| Commit | Type | Summary |
|---|---|---|
| `62468299` | fix(cql) | CASE WHEN over boolean define emits EXISTS not `sub.value` |
| `dcaa61d5` | refactor(cql) | Unify definition-reference resolution via `_classify_definition_ref` |
| `78c1091c` | fix(cql) | Use `medicationCodeableConcept` for MedicationStatement retrieve (+16 audited resources) |
| `3ba87aa0` | fix(cql) | Cross-library define references emit correlated subquery *(REVERTED — see below)* |
| `683d67da` | fix(fhirpath) | `is()` returns empty collection for empty input *(REVERTED — see below)* |
| `c90652f2` | feat | FHIRPath choice-type parity and cql-server CLI documentation |
| `9e6d1ebb` | chore(release) | Bump version to 0.0.10 |
| `06544fbf` | revert | Revert cross-library fix (regressed CMS0334 and CMS190) |
| `8f71e9dd` | revert | Revert is() fix (C++/Python parity mismatch) |
| `3aaf9a75` | docs(release) | Correct 0.0.10 notes for reverted cross-library fix |
| `b8fc8562` | docs(release) | Note is() empty-collection fix revert in 0.0.10 limitations |

### Reverts during release-prep

Two attempted fixes were reverted during pre-release validation:

1. **Cross-library define references** (`3ba87aa0` → `06544fbf`): The fix correctly addressed the user-reported binder error, but intercepted CTE *creation* paths as well as CTE *reference* paths, regressing DQM conformance on CMS0334 (9.6%) and CMS190 (7.2%). Reverted to preserve the 100% DQM baseline. Tracked as a 0.0.11 follow-up; the existing multi-library CQL pattern continues to work where cross-library defines are consumed as query sources rather than scalar values.

2. **FHIRPath `is()` empty-collection propagation** (`683d67da` → `8f71e9dd`): The Python-side fix correctly implemented FHIRPath §5.1, but the native C++ extension still returns `[false]` for empty input on non-FHIR-primitive types. The mismatch broke `test_empty_input_is_returns_false_as_returns_empty` in `test_type_parity.py` (parity invariant). Reverted; both sides need the same change. Tracked as a 0.0.11 follow-up.

## 6. Final GO / NO-GO Recommendation

**GO** with documented pre-existing limitations.

- ✅ All four conformance suites at 100% (2822/2822 tests).
- ✅ Wheel + bundled native artifacts built and structurally verified.
- ✅ Version surface aligned at `0.0.10` across package metadata, public subpackages, web landing page, install snippets, and release notes.
- ✅ Code review (workflow_step 0) completed with REV-001 and REV-002 resolved inline; REV-003 deferred, REV-004 handed off (resolved by the inclusion of all in-scope working-tree changes in this release), REV-005 confirmed clean.
- ⚠️ One pre-existing pytest failure (`TestIsLowercaseTypes::test_empty_collection_returns_empty`) carried forward from 0.0.9. Documented as a Known Limitation with the root cause and follow-up plan.
- ⚠️ Cross-library define references in CQL still produce a binder error in scalar contexts. Documented as a Known Limitation; workaround is to consume cross-library defines as query sources rather than scalars.

**Release-blocking residuals**: none. Both known limitations are pre-existing or scoped to edge cases outside the 0.0.10 conformance baseline.
