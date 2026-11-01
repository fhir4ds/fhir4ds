# Docs Audit Report — 0.0.13 (2026-08-26)

## 1. Notebook Execution Status

| Notebook | Result |
|---|---|
| docs/notebooks/cql.ipynb | PASS (executed in place against the 0.0.13 wheel via `--find-links ../../dist`) |
| docs/notebooks/fhirpath.ipynb | PASS |
| docs/notebooks/viewdef.ipynb | PASS |
| docs/notebooks/dqm.ipynb | PASS |

All `%pip install` snippets now pin `fhir4ds-v2==0.0.13` (measures extra
where required); no cell errors; outputs clean.

## 2. Stale Data Log (all fixed)

- 4 notebooks: install pins 0.0.12 → 0.0.13.
- `web/website/docs/examples/notebooks.md`: install snippets → 0.0.13.
- `web/website/src/pages/index.tsx`: PRODUCT_VERSION 0.0.13; "New in"
  headline → 0.0.13 pillars.
- `web/website/tests/demo.spec.ts`: v0.0.13 badge assertion; PLUS one
  pre-existing stale assertion fixed (feature-card heading "SQL-on-FHIR v2"
  did not exist in the current OR 0.0.12 landing page — aligned to the
  actual card "Full Auditability"; CI never ran this suite, same dark-CI
  theme as the release incident).
- `web/website/docs/integrations/wasm-engine.md`: stale 0.0.10 wheel
  references (prerequisites + micropip snippet) → 0.0.13.
- `web/wasm-demo/vite.config.ts`: fallback wheel name → 0.0.13.
- **Stale shipped wheel discovered**: `web/website/static/bulk-publisher-app/`
  still carried the **0.0.10** wheel (the bulk-publisher Pyodide app would
  install 0.0.10 in users' browsers!) — replaced with the 0.0.13 wheel.
- WASM wheel swap: `web/wasm-demo/public/` now ships only
  `fhir4ds_v2-0.0.13-py3-none-any.whl` (0.0.12 removed).
- Link/placeholder sweep: no `[PLACEHOLDER]`s; internal links resolved by
  the Docusaurus build (zero broken-link errors).

## 3. Audience Alignment Notes

- Landing page remains strategic (speed-first ordering intact — Columnar
  Speed, Zero Infrastructure, Full Auditability…); developer pages remain
  copy-pastable and now match the current API (the `evaluate_measure`
  DataFrame contract correction from the campaign is reflected in the
  README).
- The micropip `deps=False` rule is intact in all snippets
  (load-bearing rule verified — 4 usages, zero regressions).

## 4. Website Build & E2E

- wasm-demo rebuilt (`dist/` bundles the 0.0.13 wheel; extensions carried
  over); copied to `static/wasm-app/`.
- Website typecheck + build clean (webpack warnings are pre-existing
  asset-noise from `@duckdb/duckdb-wasm`).
- Playwright e2e on the final built site: **17/17 passed** (includes the
  deep DuckDB-under-COI initialization check, WHL-at-asset-path, SMART
  callback flows, v0.0.13 badge). This also discharges the release gate's
  deferred E2E requirement.

## 5. Draft Release Notes

Published as the `## Version 0.0.13` section of
`web/website/docs/getting-started/releases.md` (all prior sections
retained). Pillars: post-0.0.12 reliability fixes (orjson 3.12
compatibility — the published 0.0.12 wheel's breaker — numpy-safe DQM,
CLI parameter filtering, recursion scoping), medterm4ds 0.0.3 (both-extras
bound, diff-audited surface, HF revision/device notes), and the campaign's
hardening (native engine restorations, temporal validity contract, loader
error contracts, API verification), with the 2832/2832 baseline and the
carried known-limitation note.

**Verdict: READY.**
