# WASM engine parity — feasibility study (AMUX-175)

**Lane:** `wasm-parity` (worktree `.worktrees/wasm-parity`) · **Date:** 2026-11-24
**Ask (Joel, 2026-11-23):** investigate executing the full unit + e2e +
spec-compliance suites under WASM to identify engine parity gaps.
**Status:** feasibility study complete. No product code was changed; all
measurements come from throwaway probes kept in the gitignored
`.temp/wasm-parity-spike/` (see §7).

---

## 0. Verdict

**Running the suites under the real WASM engine is feasible and cheap, and the
gap is real and measurable.**

| headline | measured |
|---|---|
| Real duckdb-wasm boots headless in Chromium | **~0.45 s** in-page; extensions `LOAD` in ~0.1 s |
| Official CQL corpus on desktop DuckDB (same harness) | **2002 / 2015 = 99.4 %** |
| Official CQL corpus on real duckdb-wasm | **1873 / 2015 = 92.9 %** |
| Parity gaps (desktop passes, WASM fails) | **138 tests** — 118 missing functions, 20 wrong values |
| Browser extension binaries vs source | fhirpath **24 commits stale** (built 2026-09-19), cql **29 commits stale** (built 2026-10-24) |
| Node.js as a harness | **not viable** — `LOAD` of a WASM side module deadlocks (reproduced twice) |

Three things have to be separated, because "under WASM" means something
different at each layer:

1. **Translation** (Python in Pyodide) — pure Python, no DuckDB. Not an engine
   parity subject.
2. **Function surface** — which function names exist in the browser
   (`C++ wasm extension ∪ cql-macros.ts`).
3. **Engine** — duckdb-wasm's binder, planner and the WASM-built binaries.

Every existing "WASM" pytest gate stops at layer 2 and runs it on **desktop
x86-64 DuckDB**. No pytest file loads the shipped `.wasm` extension bundles;
the only pytest path that reaches duckdb-wasm is the Playwright
capability-matrix leg, which skips when its preview server is down. Otherwise
layer 3 is exercised only by Playwright UI journeys.

## 1. Engine topology (as measured on this branch, `b6e27cf`)

| component | what is deployed | notes |
|---|---|---|
| `@duckdb/duckdb-wasm` | `1.33.1-dev64.0` in all four web apps | `SELECT version()` in the browser = **`v1.5.5`** |
| desktop DuckDB in this lane | Python `duckdb` **1.5.6** | so the A/B below is 1.5.6 x86-64 vs 1.5.5 wasm32 |
| `fhirpath.duckdb_extension.wasm` | md5 `0e26a1aa…`, 888,663 B, **built 2026-09-19 16:46** | 24 commits have touched `extensions/fhirpath/src` + `extensions/common` since |
| `cql.duckdb_extension.wasm` | md5 `5bc222aa…`, 1,028,266 B, **built 2026-10-24 13:49** | 29 commits have touched `extensions/cql/src` + `extensions/common` since |
| deployed copies | identical md5 in `cql-cleanroom`, `cql-clinic`, `wasm-demo`, `viewing-room` `public/extensions` and `fhir4ds/devserver/static-cleanroom` | last committed in `1c2528ea6c0` (2026-10-24) |
| build artifacts | `extensions/*/build/wasm_eh/repository/v1.5.5/wasm_eh/` exist **only in the main checkout** | no fresher build exists anywhere |

This is the "stale ABI bundles" issue (AMUX-152), now quantified. The wheel
shipped to browsers is 0.0.26 while the binaries it calls are four to nine
weeks old, so the browser has translator-to-binary skew: source fixes that the
Python side assumes are simply absent in the browser.

**The WASM build is not reproducible from git.** There is no tracked emscripten
recipe and no `extensions/*/build` in a fresh worktree; `make wasm_eh` exists
only as a generated target inside the main checkout's build tree.

## 2. Suite inventory (a) — what is runner-dependent

Static scan of `test_*.py` under `fhir4ds/` (`.temp/wasm-parity-spike/inventory.py`).
"tests" counts `def test_` functions; `parametrize` is not expanded, so real
counts are higher. A file is counted in every class it matches.

| class | files | tests | meaning for WASM |
|---|---|---|---|
| total | 438 | 8,217 | |
| **translator-only** (no `import duckdb`) | 237 | 4,766 | pure Python — Pyodide-compatible by construction, no engine involved |
| **db** (imports `duckdb`) | 201 | 3,451 | the only tests where engine parity is meaningful |
| ├ `py_udf` (registers/needs Python UDFs) | 162 | 2,883 | **cannot run in the browser** — duckdb-wasm hosts no Python UDFs |
| ├ `native_load` (x86 `LOAD`, `allow_unsigned_extensions`) | 103 | 1,484 | not portable as written |
| ├ `fs` (tmp files, test data, subprocess, HTTP) | 174 | 3,132 | not portable |
| └ **wasm surrogate** (`no_python_connection`, `browser_connection`) | 23 | 249 | the portable subset — but they run on desktop DuckDB |

Per package:

| package | files | tests | translator-only | py_udf | wasm-surrogate |
|---|---|---|---|---|---|
| `cql` | 215 | 3,795 | 82 | 78 | 21 |
| `fhirpath` | 57 | 1,611 | 17 | 36 | 0 |
| `viewdef` | 22 | 701 | 4 | 16 | 0 |
| `dqm` | 16 | 221 | 2 | 5 | 0 |
| `sources` | 10 | 232 | 0 | 8 | 0 |
| `sqlquery` | 4 | 107 | 1 | 3 | 0 |
| `operations` | 12 | 180 | 1 | 5 | 2 |
| `tests` | 14 | 81 | 4 | 4 | 0 |
| `serve` | 18 | 247 | 5 | 3 | 0 |
| `matching` | 17 | 242 | 1 | 1 | 0 |
| `dedup` | 13 | 314 | 4 | 0 | 0 |
| `piqi` / `realism` / `mcp` | 11 | 209 | 4 | 0 | 0 |
| `devserver` / `cli` | 29 | 277 | 2 | 3 | 0 |

Only `cql`, `fhirpath`, `viewdef`, `sqlquery` and `operations` are browser
product surface. `serve`, `mcp`, `devserver`, `cli`, `sources`, `matching`,
`dedup`, `piqi`, `realism` are server/desktop tooling and not WASM candidates.

### Conformance runners (`conformance/scripts/`)

| runner | gate tests | engine dependency | seam | under real WASM? |
|---|---|---|---|---|
| `run_cql.py` | 1,706 (gate) | DuckDB + `register_udfs`; one `SELECT` per test | `run_test(conn, test_elem)` | **yes** — measured in §4 |
| `run_fhirpath_r4.py` | 935 | **none** — uses the pure-Python core evaluator, not DuckDB | n/a | not an engine-parity subject |
| `run_viewdef.py` | 144 | DuckDB + register; needs resource rows | `run_test(con, generator, test, resources)` | yes, rows must be shipped |
| `run_omop.py` | 38 | `fhir4ds.create_connection()` + data | `build_connection()` | yes, lower value |
| `run_dqm.py` | 47 + 73 | `FHIRDataLoader`, ValueSets, includes, C++ extension | none | subset only (see §3) |

DuckDB-level FHIRPath conformance (the R4 XML through `fhirpath()` UDFs,
native vs fallback) lives in pytest under
`fhir4ds/fhirpath/duckdb/tests/`, not in a conformance script.

### Availability gotchas

- **The official CQL corpus is not in git.** `fhir4ds/cql/tests/official/cql-tests/`
  is an untracked checkout that exists only in the main checkout (16 XML files,
  2,037 `<test>` elements). A fresh worktree cannot run CQL conformance at all.
- The copy in the main checkout does not match HEAD's pins: on desktop, 13 tests
  fail there (e.g. it expects `predecessor of 1.0 = 0.99999999` while HEAD
  deliberately returns the CQL 2.0 value `0.9`). The gate's "1706" does not
  match this 2,037-test copy either. Which revision is authoritative is an open
  question (§6).

## 3. What the existing WASM test surface covers (b)

| surface | size | engine actually executed | covers | blind to |
|---|---|---|---|---|
| `no_python_connection` gates (`cql/duckdb/tests/integration/`) | 18 test files | desktop x86-64 DuckDB + x86 C++ ext + **Python** `register_all_macros` | function-surface parity py vs C++ | real engine, TS macro bodies, WASM binaries |
| `test_wasm_translate_execute_gate.py` | ~50 literal defines | desktop | catalog presence + values, no FHIR data | everything data-dependent |
| `test_macro_sync.py` | name diff | none | `CREATE MACRO` names | **bodies**, and Python-UDF-backed names entirely |
| `test_wasm_surface_parity.py` + `wasm_surface_harness.py` | two small To*-conversion corpora | desktop | To* conversion family, spec-derived expectations | see the regex finding below |
| `test_cql20_f_lateral_portability.py` (FHIR4-15) | AST assertions | none | emitted SQL shape | whether the shape actually binds in WASM |
| Playwright: `cql-cleanroom` | 75 specs / 277 tests | **real duckdb-wasm** | UI journeys on a few fixtures | no systematic corpus |
| Playwright: `wasm-demo` / `viewing-room` | 19 / 87, 9 / 18 | real duckdb-wasm | UI journeys | same |
| pytest bridge to the browser | 1 file (`test_capability_matrix.py`) | real duckdb-wasm | 3-way envelope parity | skips without preview + node_modules |

`cql-clinic` has no spec directory of its own; the only specs that reference
it are `web/website/tests/demo.spec.ts` and `viewing-room-embed.spec.ts`, plus
`web/cql-clinic/scripts/verify_lessons.py`. These were located, not read.

**No pytest file loads a `.duckdb_extension.wasm`** (`git grep` for
`duckdb_extension.wasm|wasm_eh` over `*.py` returns nothing).

Two defects in the existing tooling surfaced while building the probe:

- `wasm_surface_harness.ts_macro_sql()` extracts macros with a regex that only
  recognises **double-quoted** TS strings. `cql-macros.ts` holds **116**
  statements; the harness registers **94**. The 22 it silently drops include
  `"Distinct"`, `IsNull/IsTrue/IsFalse/IsNotNull`, `Coalesce`, `IfNull`,
  `And/Or/Xor/Not/Implies`, `Left/Right` and the `audit_*` family. The
  "browser-equivalent surface" that gate builds is not the browser surface.
  (Observed in passing: `REGISTERED_MACRO_NAMES` has 117 entries for 116
  statements — worth a look.)
- `web/wasm-demo/scripts/test-cms-wasm-node.mjs` only loads the real extensions
  when `FHIR4DS_WASM_NODE_LOAD_EXTENSIONS=1`; by default it substitutes four
  simplified pure-SQL `fhirpath_*` stand-ins. Neither it nor
  `web/wasm-demo/test-extension-load.mjs` is referenced by any test, CI job or
  doc.

## 4. Measured parity gap (c)

### Method

`.temp/wasm-parity-spike/cql_wasm_probe.py` reuses `run_cql.py` verbatim for
translation and for pass/fail comparison, then executes every translated
`SELECT` on **both** a desktop connection (as `run_cql.main` builds it) and a
headless-Chromium duckdb-wasm page bootstrapped exactly like
`web/cql-cleanroom/src/lib/duckdb-wasm.ts` (same package, same open flags, the
shipped `.wasm` bundles, all 116 `cql-macros.ts` statements).

### Result — official CQL corpus, 2,037 tests

| | pass | fail | of which raised at execution |
|---|---|---|---|
| desktop (duckdb 1.5.6, HEAD bundles) | **2002** / 2015 | 13 | 8 |
| duckdb-wasm (v1.5.5, stale bundles + TS macros) | **1873** / 2015 | 142 | 126 |

22 tests fail translation on both engines and are excluded. 4 tests fail on
both engines (not parity gaps). 9 tests pass on WASM but fail on desktop — the
stale binary returns the value the older corpus copy expects.

| file | tests | desktop | wasm |
|---|---|---|---|
| CqlListOperatorsTest | 268 | 268 | **156** |
| CqlArithmeticFunctionsTest | 249 | 244 | 236 |
| CqlStringOperatorsTest | 98 | 98 | 94 |
| CqlAggregateFunctionsTest | 84 | 84 | 79 |
| CqlComparisonOperatorsTest | 281 | 278 | 275 |
| CqlDateTimeOperatorsTest | 320 | 317 | 319 |
| all other 10 files | 715 | 713 | 714 |

### Initial parity-gap list (desktop passes, WASM fails: 138 tests)

**G1 — unported list-equality macros (105 tests, `Catalog Error`).** The
`BROWSER_MACRO_GAP_ALLOWLIST` in `test_macro_sync.py` is not a theoretical
allowance; it takes out half of `CqlListOperatorsTest` in the browser.

| missing name | tests |
|---|---|
| `CQLListHasAllEq` | 20 |
| `CQLListContainsTemporalEq` | 16 |
| `CQLListEqualEq` | 16 |
| `CQLListHasAllTemporalEq` | 12 |
| `CQLListContainsEquivalentEq` | 9 |
| `CQLListEqualTemporalEq` | 8 |
| `CQLListMode` | 5 |
| `CQLListExceptEq`, `CQLListIntersectEq` | 5 each |
| `CQLListEquivalentEq` | 3 |
| `CQLListExceptTemporalEq`, `CQLListIntersectTemporalEq`, `CQLIndexOfTemporal` | 2 each |

**G2 — unported and NOT allowlisted (13 tests, `Catalog Error`).**
`Slice` (10) and `MatchesFull` (3) are Python-UDF-backed on desktop, so the
name-only macro-sync contract cannot see them. They were unknown until measured.

**G3 — stale `cql` WASM binary (15 tests, wrong value).** Each row matches a
native fix that landed in source after the 2026-10-24 build.

| symptom (WASM → desktop) | tests |
|---|---|
| predecessor/successor use the flat 1e-8 step, not the precision-based step (`0.99999999` → `0.9`) | 5 |
| `Round(-0.5)` → `0E-8` instead of `-1`; `Round(-1.5)` → `-1`; `Round(x, null)` → NULL (AMUX-152 #4) | 3 |
| quantity `div` keeps the operand unit instead of cancelling to `'1'` | 3 |
| `1 year ~ 12 months`, `1 hour = 60 minutes`, `1 minute = 60 seconds` → False | 3 |
| `days between DateTime(2014,1,15) and DateTime(2014,2)` low bound 16 instead of 17 | 1 |

**G4 — Python authority vs native mirror (2 tests, wrong value).**
`HighBoundary(1.58888, null)` and `LowBoundary(…, null)` return NULL in the
browser. On desktop both names are in `_PYTHON_PREFERRED_CPP_CONFLICTS`, so
the Python UDF answers (`udf/math.py::highBoundary` defaults a null
precision); the browser gets the native mirror. Whether HEAD's native code
handles a null precision was not checked — if it does not, this needs a C++
fix and not only a rebuild.

**G5 — `cql-macros.ts` body drift (3 tests, wrong value).** These will survive
a binary rebuild because the drift is in the TypeScript.

| expression | desktop | browser |
|---|---|---|
| `Combine({'a','b','c'}, null)` | `abc` | `a,b,c` |
| `Skip({1,2,3}, null as Integer)` | `[1,2,3]` | NULL |
| `Skip({1,2,3}, -1)` | `[]` | NULL |

### Harness facts that are themselves parity findings

1. **Node cannot host the real engine.** `@duckdb/duckdb-wasm` boots in Node
   (v1.5.5 in ~0.7 s) but `LOAD '<ext>.wasm'` deadlocks — reproduced with
   `registerFileBuffer` and with an absolute host path (20 s timeout each).
   A real-engine harness needs a browser context.
2. **Side modules resolve relative to the main module, not the registered
   URL.** Registering an extension at `/ext/<name>` and loading it yields
   `IO Error: Extension … is not available`; the loader fetched
   `/duckdb/<name>.wasm` (404). The extension must sit beside
   `duckdb-eh.wasm`, which is what Vite's `?url` assets do.
3. **`castBigIntToDouble: true`** (the app's open flag) turns BIGINT, HUGEINT
   and DECIMAL results into JS doubles before Arrow reaches the app. The
   cleanroom executor rescales DECIMAL afterwards. Whether an unscaled
   DECIMAL(38,8) value above 2^53 loses precision in the browser UI is
   **not measured** — flag for the first real-engine pass.
4. `duckdb_functions().internal` is true for extension functions in WASM; a
   catalog query that filters `NOT internal` sees only the 94 macros.
5. **The CMS159 lateral shape does not reproduce in isolation.** All four toy
   shapes from the FHIR4-15 note bind on duckdb-wasm 1.33.1-dev64.0: a
   correlated scalar subquery inside a `CROSS JOIN LATERAL` projection, a
   lateral correlated two levels up, a correlated `EXISTS` in a lateral `WHERE`.
   The translator-side fix stands, but its regression test is AST-shape-only
   and no real-engine test replays the SQL that failed.

### Not measured

- FHIRPath on real WASM (the fhirpath bundle is the oldest artefact, and it
  predates the 2026-11-15 alignment with the refreshed R4 corpus).
- ViewDefinition, OMOP and DQM on real WASM.
- Whether HEAD-translated measure SQL emits November native names
  (`RoundQuantity`, `RoundQuantityTo`, `Comparable`, `cqlEquivalentInValueset`)
  — the strings are absent from the shipped `cql` bundle; the CQL corpus does
  not emit them, measure SQL was not generated here.
- WASM memory/time on large measures (wasm32 address space; CMS2 SQL is 1.5 MB).

## 5. Gap-closure plan

Sequenced so each phase ends with a measured number.

| # | deliverable | est. | acceptance |
|---|---|---|---|
| **P0** | Real-engine harness in-repo: a static `harness.html` (boot flags copied from `duckdb-wasm.ts`), served with COOP/COEP; a Python `WasmEngine` client over Playwright (boot once per session, `run_batch`); a `WasmRemoteConnection` shim (`execute/fetchone/fetchall`) with typed value reconstruction; pytest marker that skips cleanly without node_modules/chromium | 1–1.5 d | boots < 2 s; smoke green; zero skips-as-pass |
| **P1** | Rebuild `wasm_eh` for cql + fhirpath from HEAD; redeploy to the four apps + `devserver/static-cleanroom`; rebuild cleanroom dist. Add `test_wasm_bundle_freshness.py` (bundle must be newer than the last commit touching `extensions/*/src`), the WASM twin of `build_extension_bundles.py --verify` | 0.5–1 d | md5s change; G3 (15 tests) → 0 on the harness |
| **P2** | Close G1 + G2: port the 15 names to the C++ extension (S32 doctrine: prefer C++; keep a TS macro only with a behaviour test). Extend `test_macro_sync.py` so the contract is "every function name the translator can emit exists in `C++ ∪ TS`", computed from an emission inventory over the corpora | 2–4 d | `CqlListOperatorsTest` 268/268 on the harness |
| **P3** | Behaviour parity tests for every `cql-macros.ts` macro against desktop on null/empty/negative inputs; fix or port the G5 three | 1–2 d | G5 → 0 |
| **P4** | Spec legs on real WASM through the shim: `run_cql.py`; `run_viewdef.py` (ship resource rows); the DuckDB-level FHIRPath R4 pytest corpus (collect → batch); OMOP; a DQM smoke subset (CMS159 plus large measures for binder/memory) | 2–3 d | per-suite WASM report next to the desktop report |
| **P5** | Wire the WASM legs into the release gate as a separate report; promote to blocking once P1–P3 have landed | 0.5 d | `run_all.py` prints both |

Total ≈ **7–11 lane-days**. First checkpoint — P0 + P1 + the `run_cql` leg,
with the before/after number — in about **3 days**.

What is deliberately **not** planned: porting the pytest suite wholesale. Of
201 db-touching files, 162 need Python UDFs and 103 load the x86 extension;
those are the desktop oracle, not WASM candidates. The 23 no-Python parity
files (~249 tests) are the only pytest subset worth running through the shim,
and the 237 translator-only files need nothing more than the Pyodide boot the
cleanroom already performs on every page load.

## 6. Decisions needed

1. **Corpus authority.** Which `cql-tests` revision is the gate's reference?
   The main checkout's copy (2,037 tests) disagrees with HEAD on 13 tests and
   with the documented 1,706 total. Default taken: report against the
   main-checkout copy and say so.
2. **Where to rebuild.** The only emscripten build tree is in the main
   checkout, which another lane owns. Either that lane runs the `wasm_eh`
   build, or this lane recreates the toolchain (needs `extension-ci-tools` and
   a large emsdk download on the shared link). Default taken: not rebuilt;
   P1 is blocked on this.
3. **G1 strategy.** C++ port or verbatim TS macros for the list-equality
   family. Default taken: plan assumes C++ (S32 doctrine).
4. **Gate policy.** Advisory report first, blocking later. Default taken:
   advisory in P4.

## 7. Reproduction

Scratch files live in `.temp/wasm-parity-spike/` (gitignored):

| file | role |
|---|---|
| `www/harness.html` | the page: boots duckdb-wasm, loads both bundles, registers macros, `run(stmts)` |
| `serve.py` | stdlib static server on 127.0.0.1 with COOP/COEP |
| `run-playwright.mjs` | drives the page for one JSON job |
| `spike.mjs`, `worker-wrapper.cjs` | the Node attempt (documents the `LOAD` deadlock) |
| `cql_wasm_probe.py` | the CQL-corpus A/B (§4) |
| `inventory.py` | the static suite scan (§2) |
| `out-browser.json`, `cql-wasm-records.json`, `inventory.json` | raw results |

The page needs an import map for `apache-arrow`, `tslib` and `flatbuffers`, and
symlinks to a checkout's `node_modules/@duckdb/duckdb-wasm/dist` for
`duckdb-browser.mjs`, `duckdb-browser-eh.worker.js` and `duckdb-eh.wasm`. The
extension `.wasm` files must be symlinked **into the same directory** as
`duckdb-eh.wasm` (finding 2 in §4).

To re-run the measurement: start `serve.py 5199 <www>`, then

```bash
PYTHONPATH=$REPO python3 cql_wasm_probe.py $REPO <cql-tests dir> . \
    <cleanroom>/node_modules/playwright 5199
```

## 8. Limits of this study

- One corpus measured end to end (CQL). The other suites are classified, not
  measured.
- Desktop baseline is duckdb **1.5.6**, not the gate's 1.5.5, because that is
  what this lane's Python imports.
- G3 is attributed to bundle staleness by date and by matching symptoms to
  commit titles; it was not confirmed by rebuilding. G4 (2 tests) is
  attributed by the registration path only.
- Inventory counts are static and per-file; they size the problem but are not a
  test count.
- The e2e specs were counted, not read; "UI journeys" is from the cleanroom
  `AGENTS.md` doctrine, not from auditing each spec.
