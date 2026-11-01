# Release Readiness Report — v0.0.14

**Verdict: GO.**

## Version bump (0.0.13 → 0.0.14)

- `pyproject.toml` version = 0.0.14 ✓
- medterm4ds pins: `>=0.0.4,<0.0.5` in BOTH extras (terminology → medterm4ds,
  ner → medterm4ds[extraction]); MT-001 comment updated to <0.0.5 ✓
- All 7 `__init__.py` `__version__` sites = 0.0.14 (test_version 2/2) ✓
- Notebook install pins (cql/dqm/fhirpath/viewdef.ipynb) → 0.0.14 ✓
- Website: PRODUCT_VERSION, hero blurb, notebooks.md, wasm-engine.md,
  wasm-demo vite.config fallback wheel name → 0.0.14 ✓
- releases.md v0.0.14 section added (WASM C++ parity + resolve() fix +
  medterm4ds 0.0.4) ✓

## medterm4ds 0.0.4 coordination

- Team confirmed (2026-09-09): NOT yet tagged; candidate wheel
  `medterm4ds-0.0.4-py3-none-any.whl` (Sep 7 11:19) built from dev HEAD
  d464d10 = the 0.0.4 runtime surface (9 uncommitted files are docs/tests
  only). Release awaiting human tag/merge/upload; team will notify on tag.
- Decision (per plan + team recommendation): proceed with the candidate
  wheel. MT-001 battery was validated against this exact wheel earlier in
  the campaign (in_process adapter 57/57, autocoding/notes suites pass,
  DQM 188/188 under in_process mode). Re-verify against the final tag when
  it lands (followup tracked in handoff with medterm4ds session).

## Wheel

- `dist/fhir4ds_v2-0.0.14-py3-none-any.whl` (10,844,712 bytes), built via
  hatchling (hatch CLI has an unrelated EnvVars/None crash on this box —
  worked around by invoking the cached hatch-build venv's hatchling
  directly; build hook re-bundled both extensions from
  build/release/repository).
- Bundled binaries md5 == repo bundles == site-packages:
  - cql.duckdb_extension 30c79e71c51b (campaign build, 10 ports)
  - fhirpath.duckdb_extension 39bea4784618 (unchanged)
- METADATA: Version 0.0.14; medterm4ds pins present on both extras.

## Clean-venv validation

- Fresh 3.10 venv: install OK, `fhir4ds.__version__` == 0.0.14,
  `create_connection()` + native cqlDivide('10.0','3.0') == 3.33333333,
  cqlChildren transport markers OK, `pip check` clean.
- 3.11 venv (uv 3.11.10): 0.0.14 wheel installs (--no-deps over the
  validated 0.0.13 dep set), version 0.0.14, site-packages cql ext md5 ==
  campaign binary, register_cql + cqlDivide native OK, `pip check` clean.

## Gates

- Master conformance (post-bump, release state): **2832/2832** (ViewDef
  144, FHIRPath 935, CQL 1706, DQM 47) — first pass.
- Campaign parity suites: 223 assertions green (6 new files) + loader 91 +
  message 13 + wasm gate/conversion/forced-backend 15.
- Evolution phase: 15/15 iterations PASSED (domains 6-10; 1 HIGH bug fixed
  — resolve()/Trim shadowing; 1 pre-existing Avg JSON-integer issue
  flagged for the next CQL chunk owner).
- Code review #2: CLEAN_WITH_NOTES (REV-v14-006 `__all__` fix applied
  in-review; ledger carried).

## Known limitations / notes for docs_audit

- cqlDateTimeAdd + ratioCompare: Python remains desktop conformance
  authority (documented divergent input classes); C++ scalars serve
  no-Python/WASM. Surfaced in AGENTS.md + plan.
- REV-v14-004 (fhirpath one.ln()/zero.sqrt() bool False-vs-None): source-
  level, owner FP-11, outside this release's scope.
- cql-clinic/ is a NEW untracked web app (sibling effort) — scribe decides
  staging; it ships both wasm extensions at md5 parity.
- WASM/website surface (wheel copy to wasm-demo/public, static/wasm-app
  snapshot, e2e reruns) assigned to docs_audit per directives.

---

# Re-Audit — 2026-09-17 (pre-commit, full ROLE_RELEASE_ENGINEER pass)

Trigger: wheel+sdist rebuilt (hatch), cql-clinic dist rebuilt + deployed to
website static, fresh wheel synced to all four static app dirs, cql-clinic
hidden from website nav (not ready), bulk-publish spec realigned to the
reworked example. Joel pushes/merges after this commit.

## Build Status
- C++ native: `cmake --build build/release` 100% for BOTH extensions.
  Relinked binaries byte-identical to wheel-bundled copies (fhirpath
  39bea478…, cql 30c79e71…) — deterministic rebuild confirmed.
- Wheel+sdist: `hatch build` green, both extensions bundled. GOTCHA
  CONFIRMED: `python -m build` builds the wheel from the extracted sdist,
  where the source-tree discovery hook finds NO binaries and silently ships
  Python-fallback-only. `hatch build` (source tree) is mandatory.
- WASM: deployed .wasm pair (Sep 9) postdates all C++ source edits; native
  relink byte-identical ⇒ parity holds without a WASM rebuild.

## Artifact Gate (all green)
- METADATA 0.0.14, duckdb==1.5.2 + numpy + pint>=0.21.0, medterm4ds
  >=0.0.4,<0.0.5 both extras; both native artifacts bundled.
- Clean venv install: pip check clean, site-packages resolution, 0.0.14.
- C++ proof: flags {True, True}; fhirpath_text/number, quantityValue,
  valueset cache add/size/clear, in_valueset all correct (quantityValue on
  string-encoded values → None matches upstream py/cpp parity).
- API matrix incl. repeated register: pass. Hostile collision
  (pre-created fhirpath_text): no crash, degrades {False, False}.
- Unsupported duckdb 1.4.2 (force-reinstall over the pinned 1.5.2): flags
  {False, False}, Python fallback serves representative UDFs.
- Wheel checksum: dist/ == wasm-demo/public == cql-clinic/public == all
  website static app copies (single md5).

## Test Coverage
- Conformance master gate: 2832/2832 — exact baseline (see verbatim block
  in ARCHIVE_LOG/PROC_VALIDATION: ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47, OVERALL 100.0%).
- Unit suite: 9913 passed / 11 skipped / 5 failed. The 5 failures are
  PRE-EXISTING at HEAD 0.0.13 (verified in a HEAD worktree): 3× structural
  list-selector strictness, 1× ratio tuple selector, 1× math_parity
  (FP-11-owned). One transient failure during the audit (list_part2
  historian_count) was a cmake-relink truncation race and passes 48/48 in
  isolation. Do not run the parity suite concurrently with `cmake --build`.
- Playwright e2e (web/website): 19/19 after realigning bulk-publish.spec.ts
  to the reworked example (H1 "Bulk Publish" from MDX body; five section
  H2s now live in the MDX article, not inside .bulk-publish-demo-app).
- DQM known fixtures (CMS1017/135/145/157) all 100.0% — unchanged vs the
  committed 0.0.13 report (improvement predates this cycle; PROC_VALIDATION
  "known upstream" figures are stale relative to current fixtures).
- Benchmark runner: not present in this checkout — deferred.

## Verdict: GO (re-affirmed)
All four conformance gates at baseline, artifact gate fully green, e2e
19/19, blockers empty. Advisories: the 5 pre-existing unit failures (next
chunk owner), the `python -m build` bundling trap, and the build-vs-test
race note above. cql-clinic remains hidden from nav until ready (page
unlinked, not deleted).
