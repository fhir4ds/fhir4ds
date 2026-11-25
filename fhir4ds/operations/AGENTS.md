# fhir4ds.operations + fhir4ds.mcp — AGENTS.md

## Purpose

The operations layer defines every user-facing engine capability **once**
(`fhir4ds/operations/`), returning typed, versioned envelopes
(`schema: 1`). Adapters are thin: the `verify` CLI
(`fhir4ds/cli/verify.py`), the MCP stdio server (`fhir4ds/mcp/server.py`,
optional `[mcp]` extra), and future surfaces (browser studio worker).

FDD: `fhir4ds-private/docs/architecture/plans/FEATURE_OPERATIONS_LAYER.md` (v3.2).

## Structure

- `operations/envelopes.py` — Diagnostics/DiagnosticCode/ErrorLocation,
  LibraryText/DatasetSpec/TestsInput + strict `*_from_dict` parsers,
  `_EnvelopeFields` mixin (`schema`, `ok`, `passed`, `diagnostics`).
- `operations/errors.py` — total engine-error → code mapping
  (`diagnostic_from_exception`); `OperationError` for internal call-shape
  errors.
- `operations/library_sources.py` — §3.3.1 resolution chain: inline →
  bundled (`importlib.resources` over `fhir4ds/cql/resources/cql/*.cql`)
  → adapter extras → typed NOT_FOUND. Explicit beats implicit (inline
  overrides bundled same-name).
- `operations/capabilities/` — parse (`include_ast=True` exposes a
  dataclass-walked statement-tree dict), translate (stateless;
  `audit_mode` = none|population|full + `patient_ids` pushdown +
  `output_columns` aliasing — output_columns/patient_ids require the
  population shapes and are rejected on the CTE shape);
  dataset_ops, evaluate, run_tests, explain (conn-taking);
  validate.py (`validate_resource` — loader-guard reuse, validate⇒loads
  invariant) and schema.py (`resource_schema` — R4 StructureDefinition
  snapshot reader) added by the CQL Cleanroom cycle (stateless);
  compare.py (`compare_evidence` — baseline/current population diff;
  `evidence_payload_from_dict` STRICTLY accepts a single
  EvidenceResult envelope, a `{"patients": {...}}` collection, or a bare
  `{pid: {"populations": ...}}` map — anything else is an input_error
  naming the found shape; `null` populations are preserved (flipped
  domain); rows sort deterministically patient-then-column).
- `mcp/server.py` — FastMCP stdio; `build_server()` is the test seam.
  stdout is redirected to stderr at boot (JSON-RPC owns stdout).
  Single active dataset; stale handles → typed `not_found`. Session
  include cache under caller-supplied libraries (explicit wins).
  `compare_evidence_tool` is stateless (no dataset handle).
- Browser adapter: `web/cql-cleanroom` (third adapter after CLI/MCP) —
  Pyodide runs the stateless capabilities; duckdb-wasm executes the
  translated SQL behind a TS executor emitting the same schema:1
  envelopes (exact-SQL doctrine: SQL runs VERBATIM; no client-side
  rewriting). Parity is enforced by the three-way matrix legs
  (run_tests AND compare_evidence) and the vitest envelope-parity
  gate. E2E needs the built app served on :5176
  (`npx vite preview --port 5176 --strictPort`); legs skip cleanly
  when tooling/preview is absent.
- Macro sync: `operations/tests/test_macro_sync.py` diffs the Python
  macro surface (`cql/duckdb/macros/*.py`) against
  `web/cql-cleanroom/src/lib/cql-macros.ts`. Unported macros must
  either be ported or added to `BROWSER_MACRO_GAP_ALLOWLIST` (with
  justification) — the allowlist itself is contract-checked (stale
  entries and silently-ported entries both fail).
- CLI: `verify --evidence PATH` writes the multi-patient populations
  artifact; `verify --baseline PATH` compares it against the current
  evaluation (exit 2 on missing/invalid baseline file).

## Rules

- **Adapter-only**: no engine module modifications. Operations import
  existing public APIs (`parse_cql`, `evaluate_measure`,
  `FHIRDataLoader`, translator); adapters import operations only.
- **No session/argv/process state in operations core** — operations are
  `(inputs, conn) -> envelope`.
- **Codes are the contract**: every failure path yields
  `Diagnostics(code=...)`; `detail` carries type names; structured
  engine fields (`expected`/`found`, `symbol`, `feature_name`) ride in
  `data` — never regex message strings.
- **`ok` vs `passed`**: `ok` = execution succeeded; `passed` = test
  assertions held (run_tests only). CLI exit 1 covers both.
- **TIMEOUT code is reserved** — never emitted in v1 (no fake
  cancellation around DuckDB); `--timeout-seconds` is validation +
  wall-clock reporting only.

## Known fragile areas

- `evaluate.py:_evaluate` materializes inline libraries to a temp dir
  because `evaluate_measure` is path-based; `dataset=None` means "use
  the connection's loaded state" (MCP post-load flow).
- `explain_patient` unwraps audit-dict population values
  (`{'result': bool, 'evidence': [...]}`) — audit_mode="full" shape.
- `run_tests` resolves case targets through output_columns THEN raw
  column names THEN define-name columns; unknown patient/define is a
  case failure with `reason`, never a crash.
- The capability-matrix test
  (`operations/tests/test_capability_matrix.py`) is the parity
  definition: CLI subprocess vs in-process MCP client vs the browser
  cleanroom leg (vite preview on :5176, env-injected fixture) on the
  shared fixture. Adapter changes must keep it green; the cleanroom leg
  extends it without changing the fixture. The cleanroom leg skips on
  environment availability (no npx/node_modules/preview).
- **Macro-sync contract**
  (`operations/tests/test_macro_sync.py`): every `CREATE MACRO` name in
  `fhir4ds/cql/duckdb/macros/*.py` must be registered in
  `web/cql-cleanroom/src/lib/cql-macros.ts` (or listed with
  justification in `BROWSER_MACRO_GAP_ALLOWLIST`). Allowlist hygiene is
  enforced both directions (stale entries fail; silently-ported entries
  must leave the allowlist). New translator macros that reach population
  SQL MUST be ported in the same change.
- **translate_cql modes**: `audit_mode='none'` (CTE shape) |
  `'population'` (plain-boolean population SQL) | `'full'` (audit
  structs + patient_ids pushdown); `output_columns` aliases final
  columns (population/full only — impossible combos raise OperationError
  → `evaluation_error` envelope). Unknown define names in
  output_columns surface the engine's error listing available
  definitions.
- `TranslateResult.column_types`/`definitions` carry cql_type_ref
  metadata; `evaluate_library` recovers it via `_definition_meta_map`
  (stateless re-translation) — do not reintroduce the degenerate
  `_column_types(None, ...)` path.

- `compare_evidence` classifications are presence-typed: `moved` =
  both-present value change; `added`/`removed` = one-side absence;
  `flipped` = bool↔null transition. `from`/`to` carry VALUES only
  (bool|null) — presence lives in the classification enum. Nulls are
  preserved end-to-end (never normalized to false).
- `evidence_payload_from_dict` is STRICT: accepts a single
  EvidenceResult envelope (with `patient_id` + `populations`), a
  `{"patients": {...}}` collection, or a bare `{pid: {"populations":`
  `...}}` map; anything else raises ValueError naming the found shape.
- CLI `verify --evidence PATH` writes the per-patient populations
  artifact; `--baseline PATH` prints the compare_evidence delta
  (missing/invalid baseline file → exit 2).
- The macro-sync contract: `operations/tests/test_macro_sync.py` fails
  CI when a new Python translator macro is not registered in
  `web/cql-cleanroom/src/lib/cql-macros.ts` and not justified in
  `BROWSER_MACRO_GAP_ALLOWLIST` (stale allowlist entries also fail).

## Validation

```bash
python3 -m pytest fhir4ds/operations/tests fhir4ds/cli/tests fhir4ds/mcp/tests -q
```

MCP tests skip cleanly when the optional `mcp` package is absent
(`pytest.importorskip`).

## WASM parity gates (Tier A + Tier B, AMUX-175 / 2026-11-24)

The browser apps run translated SQL on duckdb-wasm with **C++ wasm extension bundles plus
`cql-macros.ts`**, not on desktop DuckDB. These gates keep that surface honest.
Code: `fhir4ds/operations/tests/wasm_parity/`. Plan:
`FEATURE_WASM_PARITY_TEST_INFRA.md`. Reports: `tests/output/wasm-parity/*.{json,md}` (gitignored).

- **The reference bundle is named**: `web/cql-cleanroom/src/lib/cql-macros.ts` (116
  statements). Every `web/*/src/lib/cql-macros.ts` must be byte-identical to it (T6). It is
  loaded through node, never re-parsed by regex.
- **Two browser surfaces.** The *simulator* (Tier A) = desktop DuckDB + the x86 bundles + the
  reference statements: it proves the contract and runs the official corpora cheaply. The
  *real engine* (Tier B) = headless duckdb-wasm + the **shipped** wasm bundles: only it sees
  the binder, the planner, the Arrow transport and bundle staleness. Tier A cannot replace
  Tier B: the two fail different cases.
- **Step 0 (T1–T7)** `test_wasm_parity_step0.py`: reference parses; simulator is faithful; no
  wasm-only macros; same-name macros have equal bodies; every desktop macro is in the reference
  or natively provided; app bundles identical; shipped `.wasm` copies are one known set
  (`fhir4ds/wasm_extension_bundles.json`, `scripts/build_wasm_extensions.py --verify`).
- **Tier A** `test_wasm_parity_tier_a.py`, one ratchet test per suite, each reusing the official
  runner's own comparator: CQL (2,043 at corpus `0a8f7d3`, vendored in git),
  ViewDefinition (144), OMOP (38), and FHIRPath R4 —
  where only 3 of 1,191 tests are evaluable today (see the fragile area on XML inputs).
  Identical SQL runs on desktop and on the simulator; outcomes `GREEN`, `PARITY_GAP`,
  `BROWSER_ONLY_PASS`, `BOTH_FAIL`, `ENGINE_DIFF`, `TRANSLATE_DIFF` (must be zero, cannot be
  registered), `TRANSLATE_ERROR` (reported only).
- **Tier B** `test_wasm_parity_tier_b.py` (~30 s): B1 real catalog (macro bodies equal the
  simulation; the exact staleness list), B2 version pins, B3 curated families equal desktop,
  B4 Arrow transport envelope, B5 opt-in whole CQL corpus on real duckdb-wasm
  (`FHIR4DS_WASM_FULL_CORPUS=1`, ~35 s).

### The ledger is the policy (`known_gaps.json`)

Register or fix — never ignore. Every non-green case is attributed to the browser names its
SQL emits (a set difference on the SQL text, never error-text parsing). An unregistered gap
fails the gate and prints a ready-to-paste entry. Registrations expire (90 days; 30 for
principle kinds `TS_BODY_DRIFT` / `WASM_ONLY_MACRO` and for in-flight desktop defects). A
registration whose gap no longer reproduces fails the gate (remove it). `WASM_ONLY_MACRO`
additionally needs `approved_by`: the browser must not have a macro desktop does not have.
A **case-level entry names the surface** it was observed on (`simulator` | `real`, or none for
both); a desktop defect reproduces whenever the desktop verdict fails, whichever surface it is
compared with.

### Running

```bash
# Step 0 + Tier A + selftest (capped like every DuckDB-touching suite)
PYTHONPATH=$PWD bash scripts/capped.sh 16 8 python3 -m pytest \
  fhir4ds/operations/tests/test_wasm_surface_parity.py \
  fhir4ds/operations/tests/test_wasm_parity_step0.py \
  fhir4ds/operations/tests/test_wasm_parity_tier_a.py \
  fhir4ds/operations/tests/test_wasm_parity_selftest.py -q -p no:cacheprovider
# Tier B: WITHOUT the cap (chromium cannot start under `ulimit -v`), light
PYTHONPATH=$PWD python3 -m pytest fhir4ds/operations/tests/test_wasm_parity_tier_b.py -q
python3 -m fhir4ds.operations.tests.wasm_parity.report [--suite cql] [--tier-b]
```

`FHIR4DS_REQUIRE_WASM_PARITY=1` and `FHIR4DS_REQUIRE_WASM_REAL=1` turn "environment input
missing" skips into failures (CI). A lane worktree has no `node_modules`: point
`FHIR4DS_WASM_NODE_MODULES` at a checkout root that ran `npm install` in `web/cql-cleanroom`.

### Known fragile areas

- **Only the WASM parity files are in the PR CI job.** `fhir4ds/operations/tests` as a whole is
  not: `test_capability_matrix.py`, `test_compare_evidence.py::TestMcpCompareTool` and
  `test_api_surface_contract.py::test_all_names_importable[fhir4ds.serve]` FAIL without the
  optional `mcp` / `serve` extras instead of skipping (the first CI run that included the
  directory: 7 failed, 4,361 passed). The ViewDefinition gate needs `jsonschema` (the official
  runner's report validation); CI installs it, and the gate reports it as a missing input.
- **Chromium and the memory cap.** `scripts/capped.sh` sets `RLIMIT_AS`; chromium's V8 sandbox
  reservation then fails with SIGTRAP. The engine detects a capped address space and reports an
  environment input (run Tier B uncapped). The hard limit cannot be lifted for a child.
- **Each real-engine job is a fresh browser and a fresh in-memory database.** Nothing registered
  in one job survives into the next: `RealWasmEngine.use_reference()` re-registers the
  reference macros in every boot. Statements that must share state (CREATE, INSERT, SELECT) go
  in ONE `run([...])` call.
- **Wasm side modules resolve relative to the main `duckdb-eh.wasm` directory**, not the
  registered URL: the bundles must be staged beside it (`real_engine._stage`).
- **Move values as VARCHAR + `typeof()`.** Under the apps' `castBigIntToDouble` flag the Arrow
  path rounds BIGINT/UBIGINT silently beyond 2^53 and delivers HUGEINT/DECIMAL as the UNSCALED
  128-bit limbs (scale dropped) and DATE/TIMESTAMP as milliseconds (B4 pins this). The official
  comparator receives values rebuilt from text (`run_cql.rebuild_test_value`); its list/struct
  text parser is the only place that rendering is interpreted.
- **Attribution must see quoted calls.** Translated SQL emits `"Distinct"(...)`, and
  `"Coalesce"(NULL, 1)` hides a browser macro behind a builtin spelling the shared helper
  ignores. `surfaces.emitted_names` collects quoted calls itself.
- **`CREATE MACRO IF NOT EXISTS` is silent in the browser.** A reference statement whose name
  collides with an engine builtin (`Abs`) does not create a macro and does not fail; T1's
  "every statement executes" cannot see it. Names that must be the bundle's own need
  `CREATE OR REPLACE MACRO`.
- The official runners rewrite tracked `conformance/reports/*` when executed: restore them
  (`git checkout -- conformance/reports`) after a byte-identity check.
- **The FHIRPath R4 suite on the native UDF surface is 3 tests, not 1,038.** 999 R4 tests use
  XML example files; FHIR XML carries every value as a string attribute and the native
  `fhirpath` UDF reads JSON types, so `Patient.active` arrives as `"true"` and
  `Patient.active.is(boolean)` is false — the Python core passes because it coerces by
  model type. The first run filed 119 of those as desktop defects; they were the harness.
  The evaluator now holds them back and says why (`gated_reasons`), along with tests that
  expect an error (the UDF surface is non-strict by doctrine). Unlocking them needs a typed
  FHIR XML-to-JSON conversion for the examples (two are project fixtures with no upstream
  JSON twin). Until then real FHIRPath coverage is Tier B's `fhirpath_udf` family.
- Suite evaluators share one connection per surface: each owns its `resources` table shape
  (`CREATE OR REPLACE`). `conformance/scripts/*.py` import their siblings as top-level modules.

### Tier C — real measure population SQL on real duckdb-wasm (2026-11-24, now a gate)

`wasm_parity/tier_c.py` + `test_wasm_parity_tier_c.py`. Per measure: translate and run it on
desktop through the DQM conformance harness (in a CAPPED child process — one process per
measure bounds the loader's memory), export every table the SQL reads plus the ValueSet codes,
and in ONE real-engine job create them, insert the rows, fill the native ValueSet cache the way
the loader and the cleanroom app do, and run the IDENTICAL SQL. Compare per patient and column
as text: a boolean column that differs, a different patient set or a different value is a gap;
another list order or another instant spelling (`2025-10-01 08:00:00+00:00` vs
`2025-10-01T08:00:00.000Z`) is not. A failing measure must be registered in `known_gaps.json`
as a case-kind entry with `suite` (`qi-core-2025`, `us-core-2025`) and `surface: "real"`; a
fixed measure makes its registration STALE and the gate refuses until it is deleted.

- **Per PR** (cleanroom job in `ci.yml`): the curated set `tier_c.CURATED` — small fast measures,
  CMS159 (the FHIR4-15 repro) and the three measures that carry a known real-only defect, so a
  fix flips them and the ledger flags the registration.
- **Scheduled** (`conformance.yml`, `wasm-parity` job): `FHIR4DS_WASM_TIER_C_SUITE=qi-core-2025`
  runs all 47 measures (~210 s on the real engine here, plus one desktop translation each).
- Tier C is the referee for defects the name-level gates cannot see: a C++ BEHAVIOUR fix adds no
  function name, so Tier B's staleness check stays green while the browser still runs the old
  logic until the wasm bundles are rebuilt.

What the first suite-wide run found (QI-Core 2025, dev `a9845673e87` + rebuilt bundles; 45
measures ran, 24 byte-identical, 19 equal apart from list order / instant spelling):

- **CMS75 is WRONG in every browser (FHIR4-47).** Patient `f076026e-…` is in the Numerator on
  desktop and not on real duckdb-wasm (2 vs 1). A zero-width prevalence interval with a `Z`
  suffix sits exactly on the Measurement Period start; the Python `intervalOverlaps` says TRUE,
  the native one (x86 AND wasm) says NULL for a Z-suffixed bound against an offset-less peer.
  Browsers have no Python, so they are wrong.
- **CMS56 and CMS832 CRASH in every browser (FHIR4-48).** `More than one row returned by a
  subquery used as an expression`: the generated SQL has scalar subqueries that return several
  rows. The desktop DQM harness only survives because
  `fhir4ds/dqm/tests/conformance/database.py` sets
  `scalar_subquery_error_on_multiple_rows=false`; no web app does. Decision (fhir4ds lane):
  fix the lowering, never set the flag. **FIXED on dev 2026-11-25** (the lowering now emits
  single-row scalar subqueries): the next Tier C run on the merge found desktop and the real
  engine in agreement for both measures, flagged the two registrations STALE, and they were
  deleted. That flip is the gate doing its job: a registration is a claim about today, not a
  record of history.
- **ValueSet membership is EMPTY in three of the four apps (FHIR4-49).** Cold,
  `in_valueset(resource, path, url)` returns NULL for every row and every valueset-filtered
  retrieve is empty, with no error: the native function reads an in-process cache that only
  `cql_valueset_cache_add` fills. The desktop loader fills it; at the time only
  `web/cql-cleanroom` did (`src/lib/valuesetBridge.ts`). With the cache
  filled CMS159 gives 66 of 67 patients byte-identical to desktop (the 67th differs only in the
  order of an evidence list). **FIXED on dev 2026-11-25**: all four apps seed the cache through
  the shared `web/shared/valuesetBridge.ts` and banner an unseeded url (root `AGENTS.md`,
  "Browser ValueSet cache"). The gate still warms the cache itself, so it measures the engine,
  not the app wiring.
- **DuckDB prunes an unused scalar projection.** `SELECT count(*) FROM (SELECT
  cql_valueset_cache_add(...) FROM valueset_codes)` NEVER runs the function, because nothing
  reads its result. Any app code that loads ValueSets through an unread projection silently
  loads nothing.
- The CMS159 bind failure that motivated FHIR4-15/16 does not reproduce: the full population
  SQL binds and runs on real duckdb-wasm.
- Cost: INSERT literals carry ~98k codes in a few seconds; fine for a suite run. A bulk path
  (register a file buffer and `read_json`) only matters if the payloads grow.

### Rebuilding the wasm bundles — what the first real run taught (2026-11-24)

`python3 scripts/build_wasm_extensions.py --build --extension cql|fhirpath -j 4` under a cap
(one at a time; ~1–2 min each here). Its first real run failed four times before it built;
every failure is now fixed in the script, and each is a trap for anyone rebuilding by hand:

- **No `cmake --fresh`.** The emsdk environment puts the system CMake 3.22 on the path and
  `--fresh` needs 3.24. The script parks the existing build directory instead (and restores it
  in `finally`, like `scripts/build_extension_bundles.py`).
- **Declare the platform.** Without `DUCKDB_CUSTOM_PLATFORM=wasm_eh` and
  `DUCKDB_EXPLICIT_PLATFORM=wasm_eh` the build compiles a probe and tries to RUN it to detect
  the platform, and that fails here.
- **Quote every configure argument.** `CMAKE_CXX_FLAGS` holds two flags with a space between
  them; unquoted through a shell it splits, `-fwasm-exceptions` reaches the compiler and
  `-DWEBDB_FAST_EXCEPTIONS=1` is silently dropped as an unused CMake variable. That flag governs
  exception interoperability with the browser engine, so the bundle would load and misbehave.
- **The emsdk environment is needed for the link step too**: the link rule calls `emcc` by name.
- **DuckDB sources without the network.** `dev` carries no gitlink for
  `extensions/*/extension-ci-tools`, and a plain `git submodule update --init` clones DuckDB
  over the network. An object-sharing clone of another checkout's copy works offline:
  `git clone --shared --no-checkout <other>/extensions/cql/duckdb extensions/cql/duckdb`,
  then check out the recorded commit; the `v1.5.5` tag comes with it. Remove the clone afterwards
  (800 MB per extension).
- **A rebuild makes every other tracked copy stale.** The built website snapshots
  (`web/website/static/{cql-cleanroom,cql-clinic-app,wasm-app,viewing-room-app}/{assets,extensions}`)
  and `fhir4ds/devserver/static-cleanroom/{assets,extensions}` hold copies of the bundles. They
  are in the manifest's `install` lists, so the script keeps them identical (the same bytes an
  app rebuild would produce for that one file). BulkPublishDemo's copies are deliberately NOT
  installed: it pins a different duckdb-wasm version (ledger: `bundle-drift-bulk-publisher`).
- `--verify` exits 1 while BulkPublishDemo's drift exists; that is the intended signal.

### Baseline recorded (dev `87bece82a55`, corpus `f724ee4`, 2026-11-24)

- Contract: 116 reference statements; 1 wasm-only macro (`Coalesce`); 53 same-name macros with
  a different body; 33 desktop macros with no browser counterpart; 73 names where the browser
  runs a native namesake of a desktop macro; 2 app bundles differ from the reference.
- Tier A CQL: 1,818 GREEN, 126 PARITY_GAP, 60 ENGINE_DIFF, 6 BOTH_FAIL, 22 translate errors.
- Tier A ViewDefinition 144/144 and OMOP 38/38 GREEN.
- Real engine, whole CQL corpus, BEFORE the wasm rebuild: 1,809 GREEN, 137 PARITY_GAP,
  58 ENGINE_DIFF — 17 cases were real-only and all were the stale shipped wasm bundle.
- Staleness list BEFORE the rebuild (x86 bundles provided, shipped wasm lacked):
  `comparable`, `cql_equivalent_in_valueset`, `fhirpath_equivalent_in_valueset`,
  `roundquantity`, `roundquantityto`, `cqlDateTimeEquivalentListElement`.
- AFTER the 2026-11-24 rebuild (both bundles, from dev `80a826eca2d`): the staleness list
  is empty and real duckdb-wasm gives exactly the simulator's numbers on the whole CQL
  corpus (1,816 GREEN, 126 PARITY_GAP, 60 ENGINE_DIFF, 8 BOTH_FAIL). No real-only gap is left.
- Re-triaged after the merge that vendored the corpus (`0a8f7d3`, 2,043 tests) and the rebuild
  from `9e67030c688`: simulator and real duckdb-wasm both give 1,816 GREEN, 128 PARITY_GAP,
  64 ENGINE_DIFF, 7 BOTH_FAIL, 23 TRANSLATE_ERROR, 5 gated. `CoalesceMoreThanFiveArgs` left the
  desktop-defect list there (FHIR4-44 made it a translation error) — the gate reported it as a
  stale registration, which is that rule working.
- Four reference macros are **broken everywhere**, simulator included: `AllTrue`, `AnyTrue`,
  `AllFalse`, `AnyFalse` call `system.bool_and(list)` / `bool_or(list)`, overloads no DuckDB
  1.5.x has (Binder Error).
