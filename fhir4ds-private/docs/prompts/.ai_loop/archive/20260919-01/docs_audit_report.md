# Docs Audit Report — v0.0.14

**Verdict: READY.**

## Notebooks

- All 4 (cql, fhirpath, viewdef, dqm) executed clean in-place with the
  installed 0.0.14 tree; install pins updated to `fhir4ds-v2==0.0.14`
  (`[measures]` variant on cql/dqm).

## Website

- `PRODUCT_VERSION` → 0.0.14; hero blurb → "New in 0.0.14: Full WASM C++
  Parity & medterm4ds 0.0.4".
- `releases.md`: v0.0.14 section added (WASM C++ parity, resolve() fix,
  browser DECIMAL rendering, medterm4ds 0.0.4).
- `notebooks.md`, `wasm-engine.md` wheel references → 0.0.14.
- `npm run typecheck` clean; `npm run build` SUCCESS (pre-existing
  duckdb-node dynamic-require warning only).

## WASM demo / static snapshot

- 0.0.13 wheel removed from `web/wasm-demo/public/`; 0.0.14 wheel copied;
  vite fallback wheel name updated.
- Demo rebuilt; `static/wasm-app/` snapshot refreshed (rm + full copy).
  Snapshot wasm extensions md5 == demo public copies (cql 64e75d33…).
- **bulk-publisher-app**: found shipping the STALE 0.0.13 wheel (same class
  of bug as 0.0.13's audit, which found 0.0.10 there) — replaced with
  0.0.14.
- Playwright: playground 6/6 (incl. the new `10.0 / 3.0 → 3.33` native
  cqlDivide case), web-component 7/7, **CMS measures 10/10** (never skipped).

## cql-clinic

- `verify_lessons.py`: all lessons verified (headless grading).
- Full browser run via `web/wasm-demo/clinic_lessons.mjs` against a live
  dev server: data-types PASS (10 checks), comparisons PASS (11),
  fhir-queries PASS (7) — with the rebuilt wasm binaries.
- Dev server stopped after the run.

## Residual notes for scribe / Joel

- `web/cql-clinic/` is untracked (new app, sibling effort) — include in the
  release commit set or stage separately per Joel's preference.
- Campaign probe/scratch files to EXCLUDE from any commit:
  `web/wasm-demo/{clinic_lessons,clinic_one,probe2,probe3}.mjs`,
  `web/wasm-demo/test-results/`.
- Website docs terminology links + docusaurus metadata tweaks and
  `static/llms.txt`/`robots.txt` came from the medterm4ds sibling session —
  coordinated, not reverted.
