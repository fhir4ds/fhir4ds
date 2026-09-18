# Feature Plan (v2, FINAL): WASM C++ Parity — Port 10 Python-only UDFs, Delete 3 Dead Registrations

Campaign: v0.0.14 "browser-complete" | Refined from FEATURE_PLAN_DRAFT.md v1 + ARCHITECT_REVIEW.md + second-opinion review (v2.1)
This is the implementation-ready plan. Self-audit conditions S-1..S-8 and second-opinion conditions SO-1..SO-7 are incorporated.

---

## 1. Objective

Make the 10 translator-reachable Python-only CQL UDFs available in the no-Python
WASM/browser surface by porting them to C++ in `extensions/cql`, delete 3 dead
Python registrations, and reconcile the MillisecondsBetween/WeeksBetween casing
conflict. After this feature:

- The browser (cql-clinic, wasm-demo) executes the full translated-CQL surface
  without Python — closing the "cqlDivide Catalog Error" class of gaps.
- Desktop keeps Python as the conformance authority (unchanged
  `_PYTHON_PREFERRED_CPP_CONFLICTS` doctrine; none of the 10 join that list).
- Every ported function is parity-tested across 3 execution paths: forced-Python
  fallback, native C++ (desktop), no-Python C++ (browser-style direct SQL).

## 2. Scope

### 2.1 Port to C++ (10 functions)

| # | Function | Python authority | C++ destination | Critical semantics |
|---|----------|------------------|-----------------|--------------------|
| 1 | `cqlDivide` | `macros/math.py:169-215` | `cql/math.cpp` + registration | **ROUND_HALF_UP scale-8** exact text division (NOT fhirpath's HALF_EVEN 28-digit); NULL on null/zero-divisor/non-numeric/extent; VARCHAR,VARCHAR→DECIMAL(38,8) |
| 2 | `CQLMessage` | SQL macro `macros/math.py:184+` | C++ scalar | Only `severity='error'` (case-insens.) raises `error(code‖': '‖message)` with COALESCEd non-null text; else source unchanged. Macro still shadows desktop; C++ serves no-Python. |
| 3 | `coding_matches` | `udf/valueset.py:393-439` | `cql/valueset.cpp` | (resource,path,system,code)→BOOLEAN nullable; 3VL; `_CODE_SYSTEM_ALIASES` normalization |
| 4 | `coding_matches_exact` | `udf/valueset.py:441-489` | `cql/valueset.cpp` | absent-literal-element-must-be-absent semantics |
| 5 | `fhirpath_in_valueset` | `udf/valueset.py:575-667` | `cql/valueset.cpp`, shares `g_valueset_cache` | (resource,path,url)→BOOLEAN nullable; 3VL None on null/unknown/ambiguity; String-overload empty-system ambiguity; notDoneValueSet ext (URL `http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-notDoneValueSet`); register under BOTH names `fhirpath_in_valueset` + `in_valueset` |
| 6 | `cqlChildren` | `udf/list.py:371-378` | new list module | VARCHAR→VARCHAR[] nullable; `__fhir4ds_cql_type` JSON transport markers byte-identical (CQL-05 doctrine), recursive Date/DateTime/Time/Long wrapping |
| 7 | `cqlDescendants` | `udf/list.py:371-378` | same | recursive variant |
| 8 | `cqlDateTimeAdd` | `udf/datetime.py:2279-2299` | `cql/datetime.cpp` | delegate existing C++ dateAddQuantity; re-format at INPUT precision (port `_infer_precision`/`_parse_components`/`_format_at_precision`) |
| 9 | `ratioCompare` | `udf/ratio.py:159+` | `cql/ratio.cpp` | op∈{==,!=,~,!~}; equivalence=toQuantity(left)~toQuantity(right); equality=component-wise quantityCompare with 3VL |
| 10 | `ConceptToListCode` | `udf/quantity.py:1493-1499` | `cql/quantity.cpp` | VARCHAR→VARCHAR[] nullable |

### 2.2 Delete dead Python registrations (3) + casing reconciliation

| Registration | Location | Pre-delete check |
|---|---|---|
| `ConvertQuantity` | `udf/conversion.py:501` | Verify test_conversion_check_parity.py:35 routing (convert-syntax→quantityConvert vs direct UDF); update test if needed |
| `cqlDateTimeSubtract` | `udf/datetime.py:2300,2384` | ALSO remove the `cqldatetimesubtract` entry from the skip-redundant-cast whitelist `_EMITTED_UDF_NAMES` in `translator/expressions/_temporal_utils.py:269` (same commit) |
| `cqlNormalizeTZ` | `udf/datetime.py:1876,2386` | grep zero translator refs (done: zero) |
| `WeeksBetween` (Pascal) | `udf/datetime.py:2348` | DELETE the Pascal spelling ONLY; ADD camelCase Python regs `weeksBetween` — the Python def is the sole provider on forced-Python connections (C++ absent there); native is a no-op (case-insensitive probe already resolves to C++) |
| `MillisecondsBetween` (Pascal) | `udf/datetime.py:2353` | Same: delete Pascal spelling, add camelCase Python reg |

DO NOT delete PascalCase DaysBetween/HoursBetween/MinutesBetween/SecondsBetween/YearsBetween/MonthsBetween — no C++ counterpart exists; they are the sole registrations.

**ConvertQuantity test edits required** (direct-SQL callers): `test_conversion_check_parity.py:80` (`SELECT ConvertQuantity('1000 ''mg''','g')`) and `:124` (1e100 boundary), `test_core_forced_backend_parity.py:58-59`. Replace direct UDF calls with `quantityConvert` equivalents. `CanConvertQuantity` calls `ConvertQuantity` in-process (safe, keep function, delete only the registration).

### 2.3 Out of scope

- No TS-macro fallbacks (cql-macros.ts unchanged — zero entries for the 13).
- No new `__EMSCRIPTEN__` divergent branches.
- No changes to `_PYTHON_PREFERRED_CPP_CONFLICTS`.
- No translator emit changes (names already correct).
- medterm4ds pin (pre_release scope).

## 3. Architecture

Desktop native: LOAD extension → supplements registered via `_SafeConnection` →
the 10 names now resolve to C++ (skip Python reg). No-Python: extension + SQL
macros. Forced-Python: unchanged authority. The C++ implementations must be
parity-identical to Python (INV-4 tests are the only guard — no runtime fallback).

**C++ constraints:** C++11 (cql::Optional), yyjson in `duckdb_yyjson` namespace,
ExtensionLoader::RegisterFunction, RegisterSpecialScalar pattern (cql_extension.cpp:6450-6461),
ListVector::GetData returns pointer. New helpers go in `extensions/cql/src/cql/*.{cpp,hpp}`;
registrations in the cql_extension.cpp block (~:7380+).

**Build/deploy:** native release build → copy to `fhir4ds/cql/duckdb/extensions/`
+ site-packages; `make wasm_eh` in BOTH extensions/fhirpath and extensions/cql
(emsdk 3.1.56, /home/jmontavon/emsdk); .wasm to `web/wasm-demo/public/extensions/`
AND `web/cql-clinic/public/extensions/`; md5 parity build==bundles==deployed for
each target.

## 4. Implementation Plan (ordered, 12 steps)

1. Baseline: fresh run_all.py (2832/2832) + no-op WASM rebuild to validate emsdk env.
2. C++ cqlDivide (ROUND_HALF_UP scale-8 text division) + 3-path parity tests.
3. C++ CQLMessage + no-Python tests (verify macro interplay; S-2).
4. C++ coding_matches + coding_matches_exact (shared traversal) + tests.
5. C++ fhirpath_in_valueset (g_valueset_cache; both name registrations) + tests.
6. C++ cqlChildren/cqlDescendants (marker parity mandatory, S-4) + tests.
7. C++ cqlDateTimeAdd (precision-preserving wrapper) + tests.
8. C++ ratioCompare + ConceptToListCode + tests.
9. Python deletions (S-5 check first) + casing reconciliation.
10. Native rebuild + deploy + md5 (bundle==site-packages==build).
11. WASM rebuild both + deploy both web apps + md5.
12. Validation battery: pytest integration, run_all.py gate, wasm-demo playwright
    (+`10.0 / 3.0` playground case), cql-clinic 3 lessons + cqlDivide repro.

## 5. Test Strategy

- Per-function 3-path parity (forced-Python / native-loaded / no-Python C++):
  result identity incl. NULL/None, decimal text, list shapes, transport markers.
  Location: extend `fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py`
  or new `test_wasm_cpp_parity.py`; include the cql-clinic cqlDivide repro.
- cqlDivide battery: extent values, repeating decimals (0.3/0.1), zero divisor,
  non-numeric, null propagation, TruncatedDivide TRUNC parity.
- CQLMessage: severity matrix, null code/message, source passthrough typing.
- coding_matches family: aliases, missing elements, exact absent-element rule.
- fhirpath_in_valueset: cache states, ambiguity, notDoneValueSet.
- cqlChildren/cqlDescendants: marker shapes for every transported type.
- cqlDateTimeAdd: precision preservation, month-end clamp, tz.
- ratioCompare: 4 ops × valid/invalid/mismatched.
- Gates: master conformance 2832/2832 (hard); DQM 47/47; wasm-demo playwright;
  cql-clinic lessons; binary freshness md5s.

## 6. Risks (from audit + second-opinion review) & mitigations

| Risk | Mitigation |
|---|---|
| Decimal rounding-mode drift (S-1) | Spec says HALF_UP scale-8; explicit extent/repeat probes; differential byte-equality corpus on native AND wasm_eh |
| CQLMessage macro shadowing (S-2) | Verify interplay at impl; no-Python coverage; native parity leg must run on a LOAD-only con (macro shadows C++ on macro-bearing cons) |
| Transport marker drift (S-4) | Byte-identical marker tests per type; differential golden corpus (Python vs C++); END-TO-END translated children() queries on 3 paths (marker consumers are prefix-sensitive: `_query.py:2817`) |
| ConvertQuantity test routing (S-5) | Direct-SQL test callers identified (§2.2); edit tests to quantityConvert |
| **Transitive delegation hazard (SO-R2)**: ratioCompare `~` delegates to toQuantity, cqlDateTimeAdd delegates to dateAddQuantity — BOTH are `_PYTHON_PREFERRED_CPP_CONFLICTS` (Python-authoritative *because C++ differs on some inputs*) | Composite parity tests over the KNOWN-DIVERGENT input classes for ToQuantity/dateAddQuantity (the conflict-list reason inputs); probe composed-function outputs on those exact classes |
| **fhir_loader.py macro shadow (SO-R3)**: native mode creates `MACRO fhirpath_in_valueset AS in_valueset(...)` (fhir_loader.py:1268-1271) which would shadow/replace the new C++ function | Reconcile fhir_loader.py native path (drop the macro-alias creation once C++ provides fhirpath_in_valueset); regression test: native-loaded con with populated cache resolves fhirpath_in_valueset to the C++ function |
| **Vacuous/leaky parity legs (SO-R6)**: no-Python harness `register_no_python_runtime` calls `register_all_macros` which itself creates the Python cqlDivide UDF (macros/math.py:170-177) — leg isn't Python-free until C++ pre-empts it | Per-leg implementation-identity assertions via `duckdb_functions()` (function_type/origin) proving which engine served each call |
| **Silent macro registration failure (SO-R7)**: register_all_macros swallows exceptions — a post-port doctrine flip would be invisible | Post-port assertion: CQLMessage macro still creates successfully on macro-bearing paths |
| Python side effects lost on native (S-8) | Audit: logging-only acceptable |
| emsdk env breakage | Step-1 no-op rebuild validation; emsdk 3.1.56 pin is docs-only — preflight env check |

**Second-opinion verdict (2026-09-08, recorded per auto-advance doctrine): APPROVE-WITH-CONDITIONS.** Conditions adopted: (1) fhir_loader.py reconciliation + regression test; (2) duckdb_functions() identity assertions + no-Python helper leak fix; (3) differential byte-equality corpora (markers, cqlDivide) on native+wasm_eh; (4) composite parity tests over known-divergent ToQuantity/dateAddQuantity input classes; (5) camelCase Python regs retained for forced-Python leg; (6) deletion evidence corrected (cqlDateTimeSubtract whitelist entry; ConvertQuantity test edits); (7) gate confirmed to execute loaded C++ binaries + dual-target build preflight. Not adopted silently — each verified against source before incorporation.

## 7. Rollback

Additive C++ + dead-code deletions only. Revert = restore 0.0.13 binaries +
Python registrations. No data migrations.

## 8. Approval

Per USER_DIRECTIVES auto-advance doctrine (2026-09-07): WAIT_FOR_USER_APPROVAL
gate WAIVED; /second-opinion review recorded in FDD self-audit; never adopt
silently; one re-review max; on unresolved CRITICAL/HIGH adopt the safer option
and continue.
