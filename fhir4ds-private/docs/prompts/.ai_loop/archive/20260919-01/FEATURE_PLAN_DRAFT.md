# Feature Plan Draft (v1): WASM C++ Parity — Port 10 Python-only UDFs, Delete 3 Dead Registrations

Campaign: v0.0.14 "browser-complete" | Pipeline: feature_design (step 2)
Status: DRAFT — pre self-audit

---

## 1. Objective

Make the 10 translator-reachable Python-only CQL UDFs available in the no-Python
WASM/browser surface by porting them to C++ in `extensions/cql`, delete 3 dead
Python registrations, and reconcile the MillisecondsBetween/WeeksBetween casing
conflict. After this feature:

- The browser (cql-clinic, wasm-demo) can execute the full translated-CQL surface
  without any Python fallback — closing the "cqlDivide Catalog Error" class of gaps.
- Desktop keeps Python as the conformance authority (unchanged
  `_PYTHON_PREFERRED_CPP_CONFLICTS` doctrine).
- Every ported function is parity-tested across 3 execution paths: forced-Python
  fallback, native C++ (desktop), and no-Python C++ (WASM-style direct SQL).

## 2. Scope

### 2.1 Port to C++ (10 functions)

| # | Function | Python source (authority) | C++ destination | Notes |
|---|----------|---------------------------|-----------------|-------|
| 1 | `cqlDivide` | `macros/math.py:169-215` (`_cql_divide`) | new in `cql/math.cpp` + registration | Exact Decimal division, scale-8 ROUND_HALF_UP, NULL on null/zero-div/non-numeric/extent. VARCHAR,VARCHAR→DECIMAL(38,8). |
| 2 | `CQLMessage` | SQL macro `macros/math.py:184+` + UDF fallback `udf/math.py:990` | new C++ scalar in `cql/math.cpp` (or cql_extension.cpp) | Only `severity='error'` raises: `error(code‖': '‖message)`; else returns source unchanged. Preserves source physical type. |
| 3 | `coding_matches` | `udf/valueset.py:393-439` | new in `cql/valueset.cpp` | (resource,path,system,code)→BOOLEAN nullable; 3VL; system alias normalization. |
| 4 | `coding_matches_exact` | `udf/valueset.py:441-489` | new in `cql.valueset` | (resource,path,system,code,display,version)→BOOLEAN nullable; absent-literal-element-must-be-absent semantics. |
| 5 | `fhirpath_in_valueset` | `udf/valueset:575-667` (factory) | new C++ scalar sharing `g_valueset_cache` | (resource,path,url)→BOOLEAN nullable. NATIVE PRECEDENT: `InValuesetFunc` (cql_extension.cpp:4524-4670) mirrors Python 3VL incl. empty-system ambiguity and notDoneValueSet — the new function wraps the same cache. |
| 6 | `fhirpath_in_valueset` (String overload semantics) | same factory closure | same C++ function (single VARCHAR[]/3-arg form) | Python registers ONE closure under 2 names (fhirpath_in_valueset + in_valueset). C++ gets ONE function; both names registered. |
| 7 | `cqlChildren` | `udf/list.py:371-378` | new in `cql/list_ops.cpp` (new module) or cql_extension.cpp | VARCHAR→VARCHAR[] nullable; `_encode_structural_item` JSON-transport markers (`__fhir4ds_cql_type`) must be reproduced in C++ (CQL-05 doctrine). |
| / | `cqlDescendants` | `udf/list.py:371-378` | same | Recursive version. |
| 8 | `cqlDateTimeAdd` | `udf/datetime.py:2279-2299` | new in `cql/datetime.cpp` | Delegates to existing C++ dateAddQuantity then re-formats at input precision (port `_infer_precision`/`_parse_components`/`_format_at_precision`). |
| 9 | `ratioCompare` | `udf/ratio.py:159+` | new in `cql/ratio.cpp` | op ∈ {==,!=,~,!~}; equivalence via toQuantity division; equality component-wise. |
| 10 | `ConceptToListCode` | `udf/quantity.py:1493-1499` | new in `cql/quantity.cpp` | VARCHAR→VARCHAR[] nullable. |

### 2.2 Delete dead Python registrations (3)

| Registration | Location | Evidence of dead |
|---|---|---|
| `ConvertQuantity` | `udf/conversion.py:501` | Translator uses `quantityConvert` (`_functions.py:911`); no translator emit of "ConvertQuantity". CHECK at impl: test_conversion_check_parity.py:35 uses the name in a define — verify routing before deleting (replace test ref with quantityConvert if needed). |
| `cqlDateTimeSubtract` | `udf/datetime.py:2300,2384` | Zero translator refs (Subtract lowering uses dateSubtractQuantity). |
| `cqlNormalizeTZ` | `udf/datetime family` | Zero translator refs. |

### 2.3 Casing reconciliation

- C++ registers camelCase `weeksBetween`/`millisecondsBetween` (cql_extension.cpp:7543-7545).
- Python `udf/datetime.py` registers PascalCase `WeeksBetween`/`MillisecondsBetween`.
- Translator emits camelCase for both (verified `_temporal_duration.py:110-116`).
- Action: DELETE the PascalCase `WeeksBetween`/`MillisecondsBetween` Python registrations; C++ camelCase is the single registration. Non-colliding PascalCase between-family Python regs (DaysBetween etc.) stay (they are the only registration for those names).

### 2.4 Out of scope (explicitly)

- No TS-macro fallbacks (cql-macros.ts) for any of the 13 functions — none exist today; do not add.
- No new `__EMSCRIPTEN__` divergent branches.
- No changes to `_PYTHON_PREFERRED_CPP_CONFLICTS` (Python stays desktop authority for those 46).
- No translator changes to emitted names (translator already emits the right names).
- medterm4ds version pin (handled at pre_release with real 0.0.4).

## 3. Spec Alignment

- **CQL 1.5 §19.6 Divide / App B TruncatedDivide**: exact decimal semantics for cqlDivide.
- **CQL 1.5 App B §Message** (CQL-22 doctrine): only Error severity stops evaluation; source passes through unmodified.
- **CQL 1.5 §9 Equal/Equivalent** for coding_matches family and ratioCompare.
- **CQL-05 doctrine**: Children/Descendants `__fhir4ds_cql_type` transport markers.
- **CQL-02/CQL-21 clinical doctrines**: valueset membership 3VL, notDoneValueSet fallback.
- All existing pinned AGENTS.md doctrines for these functions remain binding (Python = authority; C++ must match).

## 4. Architecture

### 4.1 Registration flow (unchanged mechanics)

```
Desktop native path:  LOAD cql.duckdb_extension → _register_python_supplements(cpp_loaded=True)
                      → _SafeConnection skips create_function for C++-registered names
                      → the 10 ported functions resolve to C++ on desktop native too
                      (same pattern as the 221 existing RegisterSpecialScalar fns)
No-Python/WASM path:  C++ extension + SQL macros only → the 10 functions work in browser
Forced-Python path:   duckdb.__version__ monkeypatch → Python UDFs → unchanged (authority)
```

Key invariant: adding a C++ registration does NOT change desktop behavior because
Python supplements are only registered when the name is absent — with C++ now
providing them, `_SafeConnection` skips the Python reg, and the C++ implementation
must be parity-identical (proven by tests).

### 4.2 C++ module layout

- New/extended modules under `extensions/cql/src/cql/`: math.cpp (cqlDivide, CQLMessage), valueset.cpp (coding_matches, coding_matches_exact, fhirpath_in_valueset), list module (cqlChildren, cqlDescendants), datetime.cpp (cqlDateTimeAdd), ratio.cpp (ratioCompare), quantity.cpp (ConceptToListCode).
- All C++11-compatible (cql::Optional, no std::optional/variant/string_view); yyjson under namespace duckdb_yyjson.
- Exact-decimal long division for cqlDivide: port the approach from fhirpath's `exactDecimalRatioText` (grep -a — NUL byte hazard) OR implement scale-8 ROUND_HALF_UP division directly on text; must match Python Decimal exactly.

### 4.3 Dual-target build & deploy

- Native: `make fhirpath_loadable_extension`-equivalent for cql (existing release build), copy to `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` + site-packages; md5 parity build==bundle==site-packages.
- WASM: `make wasm_eh` in BOTH extensions/fhirpath and extensions/cql (emsdk 3.1.56 at /home/jmontavon/emsdk, source emsdk_env.sh); copy .wasm to `web/wasm-demo/public/extensions/` AND `web/cql-clinic/public/extensions/`; md5 parity across all copies.

### 4.4 Test architecture

New integration file `fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_parity.py` (or extend `test_wasm_cpp_surface.py`):
- Per function: forced-Python vs native-loaded vs no-Python C++ (direct SQL through a no-Python connection — pattern from test_wasm_cpp_surface.py).
- Include the original cqlDivide Catalog Error repro from cql-clinic.
- Each port gets at minimum: happy path, NULL propagation, error/ambiguity 3VL, edge cases per its Python authority semantics.

## 5. Implementation Plan (ordered)

1. **C++ port cqlDivide** (+ exact decimal text division; reuse fhirpath prior art). Parity tests.
2. **C++ port CQLMessage** (error severity only; source passthrough). Parity tests.
3. **C++ port coding_matches + coding_matches_exact** (share traversal helpers). Parity tests.
4. **C++ port fhirpath_in_valueset** (wrap g_valueset_cache; 3VL; notDoneValueSet via existing cql::extract_codes_with_not_done_valueset). Parity tests.
5. **C++ port cqlChildren/cqlDescendants** (transport markers). Parity tests.
6. **C++ port cqlDateTimeAdd** (delegate dateAddQuantity + precision re-format). Parity tests.
7. **C++ port ratioCompare** + **ConceptToListCode**. Parity tests.
8. **Python deletions**: ConvertQuantity / cqlDateTimeSubtract / cqlNormalizeTZ / PascalCase WeeksBetween+MillisecondsBetween regs. Verify test_conversion_check_parity routing first.
9. **Native rebuild + deploy** (cql only; fhirpath extension untouched unless needed) + md5 checks.
10. **WASM rebuild both extensions** + deploy to both web apps + md5 checks.
11. **Validation battery**: pytest integration suite, run_all.py 2832/2832, wasm-demo playwright (add `10.0 / 3.0` playground case), cql-clinic lessons verification (all 3 green; cqlDivide repro passes).
12. **Docs**: extension registration docs; cql-clinic README if it documents functions.

## 6. Test Strategy

- **Per-function 3-path parity** (forced-Python / native / no-Python C++): structural equivalence of results incl. NULL/None behavior.
- **cqlDivide exactness battery**: values at DECIMAL(38,8) extent, 0.3/0.1-style repeating decimals, zero divisor, non-numeric, null propagation, TruncatedDivide TRUNC parity.
- **CQLMessage**: severity matrix (Trace/Message/Warning pass through; Error raises with code‖': '‖message), null code/message handling, source type preservation.
- **coding_matches family**: system aliases, missing elements, exact-variant absent-element rule, multi-coding traversal.
- **fhirpath_in_valueset**: populated/unknown/empty cache, String overload ambiguity, notDoneValueSet ext.
- **cqlChildren/cqlDescendants**: nested tuple/list markers, Date/DateTime/Time/Long transport.
- **cqlDateTimeAdd**: precision preservation, month-end clamping, tz.
- **ratioCompare**: ==,!=,~,!~ over valid/invalid/mismatched ratios.
- **Gates**: master conformance 2832/2832 (hard); CQL pytest suites green; wasm-demo playwright incl. new `10.0 / 3.0` case; cql-clinic 3 lessons.
- **Binary freshness doctrine**: md5 repo==site-packages==wheel; WASM md5 build==both deployed copies.

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| C++ exact-decimal division drift vs Python Decimal | Port fhirpath exactDecimalRatioText approach; probe extent/repeating cases in parity tests |
| cqlChildren JSON transport markers drift | Copy Python `_encode_structural_item` logic verbatim; probe marker shapes |
| valueset cache 3VL drift | Reuse InValuesetFunc's proven pattern (already parity-proven for in_valueset) |
| Delete ConvertQuantity breaks test | Verify routing first (§2.2); update test to quantityConvert if needed |
| WASM build env breakage (emsdk) | Pinned 3.1.56; verify with a no-op rebuild before starting C++ edits |
| Casing deletion breaks DQM | PascalCase regs unreferenced by translator (verified); run full gate after deletion |
| FHIR4DS_PROFILE_CPP_VALUESET tests | Keep profiling hooks; new fhirpath_in_valueset wraps same cache |
## 8. Rollback

Pure additive C++ + deletions of dead code — revert to 0.0.13 binaries + Python state if parity fails. No data migrations.

---
NEXT: Step 3 architecture self-audit → ARCHITECT_REVIEW.md.
