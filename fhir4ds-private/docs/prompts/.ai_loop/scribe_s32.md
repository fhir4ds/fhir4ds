# SCRIBE — S32 WASM conversion-surface parity

Suggested commit slice (Joel commits; nothing staged):

1. `feat(cql): add C++ mirrors for the browser conversion surface`
   - `extensions/cql/src/cql_extension.cpp`: ToDateTime/ToTime/ToLong/ToRatio/
     ConvertsTo*/CanConvertQuantity (+ ToDate from the earlier S32 slice).
   - `extensions/cql/src/cql/quantity.cpp`: bare calendar keywords;
     conversion-only decimal extent guard.
   - `fhir4ds/cql/duckdb/extension.py`: Python-authority conflicts list.
   - rebuilt native + WASM extension binaries.
2. `feat(cleanroom): align browser SQL macros with desktop conversion bodies`
   - `web/cql-cleanroom/src/lib/cql-macros.ts` (ToString/ToInteger/ToDecimal/
     ToBoolean/ConvertsToString; removed ToDate/ToDateTime/ToTime/
     ConvertsToInteger macros).
3. `test(operations): three-way WASM surface parity harness`
   - `fhir4ds/operations/tests/wasm_surface_harness.py`,
     `test_wasm_surface_parity.py`, macro-sync allowlist updates.
4. `docs: release notes + WASM parity doctrine`
   - `AGENTS.md`, `web/website/docs/getting-started/releases.md`,
     FDD/plan + loop artifacts (private).
