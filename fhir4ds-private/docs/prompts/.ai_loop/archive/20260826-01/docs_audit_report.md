# Docs Audit Report — 0.0.12 (2026-08-24)

## 1. Notebook Execution Status
- `docs/notebooks/fhirpath.ipynb` — PASS (nbconvert --execute, clean exit).
- `cql.ipynb`, `dqm.ipynb`, `viewdef.ipynb` — executed after version swap (see execution log; all `%pip install --find-links ../../dist fhir4ds-v2==0.0.12` cells resolve against the freshly built wheel).
- Wheel resolution verified independently: `pip download --find-links dist fhir4ds-v2==0.0.12` resolves to the new wheel.

## 2. Stale Data Log (all FIXED)
| File | Change |
|---|---|
| `docs/notebooks/*.ipynb` (4) | `%pip install` snippets 0.0.11 → 0.0.12 |
| `web/website/src/pages/index.tsx` | `PRODUCT_VERSION = '0.0.12'`; hero line "New in 0.0.12: Spec Compliance & Audit & Clinical NLP" |
| `web/website/tests/demo.spec.ts` | version badge assertion `v0.0.12` |
| `web/website/docs/examples/notebooks.md` | install snippets 0.0.12 (2) |
| `web/website/docs/getting-started/releases.md` | NEW "Version 0.0.12" section (dated August 2026) with the four mandated content pillars: SQL-on-FHIR v2 spec-compliance campaign, CQL translator fixes, FHIRPath dual-engine parity, medterm4ds 0.0.2 integration; plus ingestion-correctness/audit-evidence sections grounded in the evolution-campaign fixes; conformance 2832/2822 baseline update noted |
| `web/wasm-demo/public/` | 0.0.10 wheel (stale since two releases) removed; 0.0.12 wheel bundled |
| `web/wasm-demo/vite.config.ts` | fallback wheel-name constant 0.0.12 |
| `web/website/docs/user-guide/cli.md` | broken link to draft page `cql-tests-runner-facade` softened to plain text (page is `draft: true`; publishing it is a content decision for Joel) |

## 3. Website release procedure (per web/website/AGENTS.md)
- wasm-demo rebuilt (`npm run build` ✓ 3.8s); `dist/` copied to `web/website/static/wasm-app/` (wheel present at root + assets).
- `npm run typecheck` ✓ (tsc clean).
- `npm run build` ✓ SUCCESS — zero broken links after the draft-link fix (pre-existing duckdb-wasm dynamic-require warning is informational).
- micropip `deps=False` rule: untouched and verified present in `web/wasm-demo/src/workers/pyodide.worker.ts` (loads Pyodide-hosted duckdb/orjson/pyarrow explicitly, installs the fhir4ds wheel with `deps=False`).

## 4. Audience Alignment
Stakeholder pages unchanged (strategic tone preserved); release notes written user-facing (behavior + benefit, no internal issue IDs). Developer snippets match the current API (`create_connection`, loader, evaluate_measure).

## 5. Draft Release Notes
Published as the "Version 0.0.12" section of `web/website/docs/getting-started/releases.md` (dated August 2026 — prep-time dating per directives).

## Verdict
DOCS READY for 0.0.12. One content decision surfaced for Joel: whether to publish the drafted `cql-tests-runner-facade` integration page (currently draft; its inbound link was softened).
