# Docs Audit Report — v0.0.16

Date: 2026-09-20
Role: docs_audit (pipeline step 4)

## Verdict: READY

## Notebooks

All four (`docs/notebooks/{cql,dqm,fhirpath,viewdef}.ipynb`) executed clean
end-to-end against the built 0.0.16 wheel installed in a fresh venv
(nbconvert --execute). Install pins updated 0.0.15 → 0.0.16 in all four.

## Website

- `web/website/src/pages/index.tsx` PRODUCT_VERSION → 0.0.16.
- `web/website/tests/demo.spec.ts` version badge assertion → v0.0.16.
- `web/website/src/components/BulkPublishDemo/workers/pyodide.worker.ts`
  wheel fallback + directory-index comment → 0.0.16 wheel name.
- `web/website/docs/examples/notebooks.md` install snippets → 0.0.16.
- `web/website/docs/integrations/wasm-engine.md` wheel references → 0.0.16.
- `web/website/docs/getting-started/releases.md` new v0.0.16 section
  (CQL type system release: TypeMapBuilder, metadata-first facade, rollback
  flag, consolidation + tripwire, 2832/2832 + byte-identical SQL guarantee).
- Typecheck clean; production build SUCCESS.
- Playwright e2e (demo.spec + wasm-demo-wc.spec incl. SMART/COI): 17/17.
- Stale 0.0.15 wheel removed from `web/website/static/bulk-publisher-app/`;
  0.0.16 wheel placed (md5 a040c7aa… == dist wheel).

## WASM demo

- `web/wasm-demo/public/` stale 0.0.15 wheel removed; 0.0.16 wheel copied
  (md5-identical to dist).
- Rebuilt (`npm run build`); `dist/` copied to `web/website/static/wasm-app/`
  (wheel served from assets/, md5-identical).
- Playwright e2e (playground.spec + web-component.spec): 13/13.
- micropip `deps=False` rule verified intact in the worker (no duckdb in the
  manual pure-Python install list).

## Consistency sweeps

- No remaining `0.0.15` references in website src/docs, notebooks, or wasm-demo
  public assets (releases.md history section intentionally retains old
  version sections).
- Wheel checksums: dist == wasm-demo/public == bulk-publisher-app ==
  static/wasm-app/assets (all a040c7aa957b4bc89bb08fd0f956c904).

## Deferred / notes

- cql-tests-runner gate: not configured in this environment (checked-in
  report remains a "not-run" placeholder) — consistent with prior releases.
- No API doc regeneration needed beyond build (no public signature changes
  beyond the additive `CQLServerConfig.metadata_first_serialization` flag,
  documented in releases.md).
