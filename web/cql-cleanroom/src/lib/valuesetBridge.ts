/**
 * PASS2 G2: ValueSet → engine cache bridge (browser worker side).
 *
 * The implementation lives in `web/shared/valuesetBridge.ts` — ONE module used
 * by every web app (cleanroom, wasm-demo, cql-clinic). This file stays as the
 * cleanroom-local import path so the worker and its unit test are unchanged;
 * it must never grow logic of its own.
 *
 * Background: the WASM `in_valueset` reads the C++ `g_valueset_cache` global,
 * NOT a SQL table. Desktop FHIRDataLoader bridges table→cache via
 * `cql_valueset_cache_add`; the browser must do the same over duckdb-wasm.
 */
export * from "../../../shared/valuesetBridge";
