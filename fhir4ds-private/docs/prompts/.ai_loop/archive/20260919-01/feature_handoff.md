# feature_handoff — v0.0.14 WASM C++ Parity (feature_implementation)

**Status: COMPLETE.** All 13 target functions ported/deleted; full validation
battery green; conformance gate 2832/2832 held.

## What was done

### 10 C++ ports (extensions/cql + registration)

| Function | C++ impl | Files | Tests |
|---|---|---|---|
| cqlDivide | `cql_divide_text` exact schoolbook long division, scale-8 HALF_UP, DECIMAL(38,8) return (hugeint memcpy) | cql/math.cpp, cql/math.hpp (CqlDivideResult), cql_extension.cpp (CqlDivideFunc, reg ~7857) | test_cql_divide_native_parity.py (34; 3000-case randomized differential + 42 hand corpus) |
| CQLMessage | `CqlMessageFunc` — condition=TRUE && lower(severity)='error' → InvalidInputException(code+": "+msg) w/ coalesce-empty nulls; else source passthrough | cql_extension.cpp | existing test_message_parity.py (13/13, incl. no-python surface) |
| coding_matches / coding_matches_exact | `coding_matches()`/`coding_matches_exact()` in cql/valueset.cpp (+ extract_simple_codes, extract_coding_dicts, code_system_alias helpers); Optional<bool> 3VL | cql/valueset.hpp/.cpp, cql_extension.cpp (4×VARCHAR / 6×VARCHAR → BOOLEAN) | test_coding_matches_native_parity.py (21; 1200-case randomized differential) |
| fhirpath_in_valueset | alias registration of the EXISTING InValuesetFunc (3VL, empty-system ambiguity scan, notDoneValueSet) under the translator's emit name | cql_extension.cpp (reg after in_valueset) | test_in_valueset_native_parity.py (8; 3-leg incl. loader reconciliation) |
| cqlChildren / cqlDescendants | `cqlstructural` namespace (IsTypedMarker, ChildrenValues, DecodeStringValue, EncodeItem/EncodeMarker); shared `CqlStructuralTraversalFunc(descendants)` driver; yyjson ESCAPE_UNICODE + lowercase-hex normalization for Python json.dumps byte parity | cql_extension.cpp | test_structural_traversal_native_parity.py (27; 800-case randomized differential) |
| cqlDateTimeAdd | `CqlDateTimeAddFunc` — dateAddQuantity guards + Python-authority Time-input rendering (0001-01-01T date prefix); added to `_PYTHON_PREFERRED_CPP_CONFLICTS` (C++ core nulls sub-input-precision s/ms where Python truncates — documented dateAddQuantity-family divergence) | cql_extension.cpp, extension.py | test_cql_datetime_add_native_parity.py (56) |
| ratioCompare | `cql::ratio_compare` — 3VL; ==/!= component-wise quantity_compare AND (Python _cql_and); ~/!~ via divide_ratio_components (quantity_divide) + quantity_compare("~"); NULL SQL ratio operands map to the Python None branches; added to `_PYTHON_PREFERRED_CPP_CONFLICTS` (C++ compound metric-prefix conversion nulls — CQL-03 QA-004 family) | cql/ratio.cpp/.hpp, cql_extension.cpp (RatioCompareFunc), extension.py | test_ratio_concept_native_parity.py (77) |
| ConceptToListCode | `ConceptToListCodeFunc` + `NormalizeCodeObjectJson` (orjson key order code/system/version/display; Quantity-lookalike rejection; codes/coding fallback) | cql_extension.cpp | test_ratio_concept_native_parity.py (subset) |

### 3 Python deletions + casing reconciliation
- **ConvertQuantity** registration deleted (udf/conversion.py); test callers
  edited to `quantityConvert` (test_conversion_check_parity.py,
  test_core_forced_backend_parity.py; the 1e100 boundary row re-expressed —
  quantityConvert converts magnitudes via pint, no extent guard).
- **cqlDateTimeSubtract** def + registration deleted
  (udf/datetime.py); skip-redundant-cast whitelist entry removed
  (translator/expressions/_temporal_utils.py).
- **cqlNormalizeTZ** def + registration deleted (udf/datetime.py).
- **WeeksBetween/MillisecondsBetween** Python registrations renamed to
  camelCase (`weeksBetween`/`millisecondsBetween`, the translator emit
  spellings; DuckDB names case-insensitive so PascalCase SQL still resolves).
  Defs kept (forced-python leg needs them).

### Deployment
- Native: cql.duckdb_extension md5 `30c79e71c51b68032095e8caa0a72b7a`
  (build == repo bundle == ~/.local site-packages; ~/.duckdb cache cleared).
  fhirpath.duckdb_extension unchanged this campaign: `39bea478...`
- WASM (emsdk 3.1.56, `make wasm_eh`, stale CMake caches wiped):
  cql `64e75d339752df447c397002a498310d`, fhirpath
  `afe07dbd747f80d19e6712e036711fbd` — build == wasm-demo/public ==
  cql-clinic/public for both. All 10 ported function names verified embedded
  in the wasm binary. (Deployed wasm was previously STALE since June 4 —
  predating even 0.0.12.)

### Web-app fixes required by the rebuilt wasm (pre-existing gaps exposed)
1. **cql-macros.ts (both apps)**: ported the 4 BENCH-001 Option D
   disambiguation macros (`cql_value_is_period`, `cql_value_is_range`,
   `cql_value_is_interval_like`, `cql_quantity_value`) from
   macros/clinical.py. Without them ANY quantity comparison
   (`O.valueQuantity.value > 140`) Catalog-errored in the browser.
2. **useDuckDB.ts (both apps)**: Arrow DECIMAL columns arrive as unscaled
   BigInt-like objects (String form drops the scale); added schema-driven
   rescale (typeId 7 + f.type.scale) so cqlDivide/Round DECIMAL(38,8)
   values display their fractional part. This was the root cause of the
   cql-clinic "Decimal Division expected 3.33333333 got 333333333" repro.
3. **playground.spec.ts**: new e2e `10.0 / 3.0 → 3.33 (display)` case
   (proves native cqlDivide + rescale end-to-end).
4. **test_wasm_translate_execute_gate.py**: stale age expectations updated
   to VARCHAR per CQL-21 §22.21 doctrine ('44'/'2', not 44/2).

## Validation results
- conformance/scripts/run_all.py: **2832/2832** (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47).
- pytest fhir4ds/cql: green except 1 PRE-EXISTING documented failure
  (test_temporal_complex_parity ratio `.numerator.value` accessor —
  CQL-20 HISTORIAN DEFERRED, owner CQL-03; deselected, plus the 3 stale
  test_structural_type_parity failures vs CQL-18 mixed-list doctrine —
  also pre-existing, stale expectations, verified pre-session).
- pytest fhir4ds/cql/duckdb/tests + fhir4ds/tests/test_version.py: 225/225
  new parity tests.
- pytest fhir4ds/fhirpath/duckdb/tests: 1767/1768 — 1 pre-existing
  SOURCE-level divergence EXPOSED by the fhirpath wasm/native rebuild
  (see Known residuals #3).
- wasm-demo playwright: playground 6/6 (incl. new divide case),
  web-component 7/7, cms-measures 10/10.
- cql-clinic browser (rebuilt extensions): all 3 lessons green
  (data-types 10, comparisons 11, fhir-queries 7 checks); the original
  cqlDivide Catalog Error repro now grades 3.33333333 exactly.
- Loader/valueset/datetime/ratio/quantity UDF unit suites: 148+61+81+12 green.

## Known residuals (NOT introduced by this campaign — flagged for owners)
1. `test_structural_type_parity.py` 3 stale tests vs CQL-18 heterogeneous
   list-literal doctrine (file Aug-20, doctrine Aug-26). Owner: translator
   list chunk. (Pre-verified failing before this campaign's first edit.)
2. `test_temporal_complex_parity.py` ratio `.numerator.value` list accessor
   (CQL-20 HISTORIAN documented DEFERRED). Owner: CQL-03 surface.
3. **fhirpath math parity `one.ln()`/`zero.sqrt()` cpp-bool False vs py-bool
   None**: the 0.0.13-era deployed fhirpath binary (39bea478, built Aug-26
   ~03:00) PREDATED the last evaluator.cpp edit (Aug-26 16:09); my wasm
   rebuild from current sources exposed the source-level divergence the
   release binary had been masking. Owner: fhirpath FP-11 rendering chunk.
   (My campaign touched zero fhirpath C++ sources.)
4. `ratioCompare` C++ (WASM-only) nulls on compound-unit metric-prefix
   equivalence (`10mg:2mL ~ 1g:200mL` → C++ False, Python True) — the
   CQL-03 HISTORIAN QA-004 deferred quantity-layer family; documented in
   the parity test as the known-divergent class. Same for cqlDateTimeAdd
   sub-input-precision s/ms inputs (dateAddQuantity family). Desktop stays
   Python-authoritative via _PYTHON_PREFERRED_CPP_CONFLICTS.

## Gotchas learned (for AGENTS.md)
- WASM build dirs (`extensions/*/build/wasm_eh`) accumulate stale CMake
  caches that break reconfigure ("System is unknown to cmake"); move
  CMakeCache.txt aside + rm -rf CMakeFiles Makefile before `make wasm_eh`.
- duckdb-wasm's Arrow surfaces DECIMAL as BigInt-like OBJECTS (typeof
  "object", String() drops scale) — rescale via schema typeId 7 + scale.
- cql-clinic mounts FRESH pyodide+duckdb workers per LessonPage — browser
  tests must wait for "Loading CQL engine"/"Loading DuckDB" to clear AFTER
  entering the lesson (~40-60s CDN pyodide init).
- yyjson emits \uXXXX uppercase hex; Python json.dumps uses lowercase —
  post-process escapes for byte parity (LowercaseUnicodeEscapes).
- Function-local `using namespace duckdb_yyjson;` does not help signatures
  in that file — qualify yyjson types in parameter lists.
