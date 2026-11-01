# DuckDB Upgrade Report — 0.0.15 cycle (2026-09-19)

## Verdict: **UPGRADED** — DuckDB 1.5.2 → **1.5.5**

## Phase 1: RECON

- Latest stable upstream release: **v1.5.5** (2026-07-22, bugfix release on the
  1.5 branch; out-of-bounds security backports, deadlock fix, RLE/json fixes).
  No major/minor release branch newer than 1.5. pip `duckdb` latest = 1.5.5.
- Release-notes scan (v1.5.3→v1.5.5): no changes to extension loading,
  scalar/aggregate registration APIs, DECIMAL/HUGEINT layout, Arrow
  conversion, JSON functions, `duckdb_functions()` introspection, macro
  shadowing, or the SQL grammar — none of our direct contact surfaces.
- **duckdb-wasm second lock**: npm dist-tags latest `1.33.1-dev64.0`
  **embeds duckdb v1.5.5** (version-badge evidence: dev41.0→1.5.1,
  dev57.0→1.5.4, dev64.0→1.5.5). Upstream duckdb-wasm CI pins
  `EMSCRIPTEN_VERSION: '3.1.71'` for `eh` bundles (3.1.57 for coi).
  Pre-existing deployed wasm side modules were built against v1.5.2 and
  loaded fine into dev41.0's v1.5.1 engine — eh side-module linking is
  patch-tolerant within 1.5.x — but we rebuild for a matched triple.

## Phase 3: BASELINE + GRACEFUL DEGRADATION (pre-work)

- Baseline gate on the OLD pin: **2832/2832** (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47).
- Throwaway venv, wheel 0.0.14 + `duckdb==1.5.5` (old 1.5.2 binary):
  bundled extension LOAD fails with the clean exact-version-lock error,
  clear warning logged, Python-UDF fallback engages, probe set
  (population SQL membership via FHIRDataLoader + CQLToSQLTranslator,
  `cqlDivide('10.0','3.0')` → 3.33333333, `fhirpath()` navigation)
  produces **IDENTICAL** results on 1.5.2-fallback vs 1.5.5-fallback.
- MD5 rollback snapshot (OLD): native cql `30c79e71c51b68032095e8caa0a72b7a`,
  native fhirpath `39bea4784618194208af4d79f0b7307e`, wasm cql
  `64e75d339752df447c397002a498310d`, wasm fhirpath
  `afe07dbd747f80d19e6712e036711fbd` (were build==repo==site-packages /
  ==all 3 web deployments).

## Phase 4: EXECUTED

1. **Submodules**: `extensions/{cql,fhirpath}/duckdb` → tag **v1.5.5**
   (commit d8cdaa33 — same commit duckdb-wasm main embeds). Nested
   submodules updated (`--depth 1`). Stale `index.lock` files from an
   Aug-11 crash removed.
2. **Native rebuild**: fresh build trees (`rm -rf build/release`; the old
   trees were the extension-ci-tools layout at `extensions/<name>/build`).
   GOTCHA rediscovered: `make release` must run from `extensions/<name>/`
   (where `extension_config.cmake` lives), NOT from `extensions/<name>/duckdb/`
   (that builds core DuckDB only). Both extensions compiled with **zero
   C++ API breakage**.
3. **Native deploy**: build → repo bundle → site-packages (both md5-matched);
   `~/.duckdb/extensions/*` caches cleared.
   - NEW native md5s: cql `18a91a6485f48cc10cc452fe2963b815`, fhirpath
     `daccb5289dd4360bbeaf68823ebec48d`.
4. **Pins/gates**: `pyproject.toml` `duckdb==1.5.5`; loader gates keep
   `startswith("1.5.")` (accepts the 1.5 series — correct for a patch bump).
   System duckdb upgraded to 1.5.5. duckdb-wasm bumped to
   `1.33.1-dev64.0` (save-exact) in BOTH `web/wasm-demo` and `web/cql-clinic`.
5. **Smoke native**: LOAD-only connection exercises cql + fhirpath UDFs;
   `cqlDivide`/`fhirpath`/`fhirpath_number` all correct.
6. **WASM rebuild**: emsdk **3.1.71 installed side-by-side** at
   `/home/jmontavon/emsdk-3.1.71` (pinned 3.1.56 at `/home/jmontavon/emsdk`
   untouched). Fresh `build/wasm_eh` trees; `make wasm_eh` from both
   extension dirs → EXIT 0.
   - NEW wasm md5s: cql `11b358b34865c231fb301c13d18e9929`, fhirpath
     `0e26a1aa3953d4c17cda25e408a9b588`.
7. **WASM deploy**: copied to `web/wasm-demo/public/extensions/`,
   `web/cql-clinic/public/extensions/`, AND
   `web/website/static/wasm-app/extensions/` (+ refreshed
   `web/website/static/cql-clinic-app/` after clinic rebuild).
   md5 parity: build == all deployments.
8. **Full gate on NEW pin**: **2832/2832** (ViewDef 144, FHIRPath 935,
   CQL 1706, DQM 47). Zero regressions — no bisect needed.
9. **Browser suites**: wasm-demo Playwright (playground + web-component +
   CMS measures) **23/23 passed**; website Playwright (demo + wasm-demo-wc +
   bulk-publish, incl. SMART callback flows) **19/19 passed** against the
   rebuilt static deployments (serve on 9372 via `PLAYWRIGHT_BASE_URL`;
   docusaurus serve takes >60s on WSL2 drvfs — start it before tests).
   wasm-demo + cql-clinic + website `npm run build` all EXIT 0; website
   `npm run typecheck` EXIT 0.
10. **Wheel + clean-venv smoke**: wheel rebuilt (0.0.14 metadata, new
    binaries); fresh venv install with `duckdb==1.5.5`: `pip check` clean,
    both extensions md5-matched inside wheel, `register()` →
    `{'fhirpath_cpp': True, 'cql_cpp': True}`, native `cqlDivide` correct.
    Python 3.11 leg: NOT runnable on this box (only 3.10 installed) —
    CI carries the 3.11 leg; flagged for pre_release CI verification.

## Collateral fix

- `fhir4ds/fhirpath/tests/unit/test_fp18_math_operators.py`: three fixtures
  hardcoded `repository/v1.5.2/` extension paths → now glob
  `repository/v*/linux_amd64/` (version-agnostic). File passes 73/73.

## Version triple (invariant 3) — verified

`pyproject.toml duckdb==1.5.5` == submodules `v1.5.5` == loader gates
(`1.5.` prefix) == duckdb-wasm dev64.0 embedded engine (v1.5.5).

## Follow-ups

- emsdk pin for wasm builds is now **3.1.71** at `/home/jmontavon/emsdk-3.1.71`
  (side-by-side; the old 3.1.56 install remains for rollback). AGENTS docs
  updated in docs_audit should record this.
- Historical release-notes references to `1.5.2` in
  `web/website/docs/getting-started/releases.md` are version-specific facts
  of those releases — intentionally NOT rewritten.
- Docs version references (wasm-engine.md etc.) and release notes for the
  0.0.15 DuckDB pin land in the docs_audit workflow per pipeline.
