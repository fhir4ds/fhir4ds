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
  runner's own comparator: CQL (2,037), ViewDefinition (144), OMOP (38), and FHIRPath R4 —
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

### Baseline recorded (dev `87bece82a55`, corpus `f724ee4`, 2026-11-24)

- Contract: 116 reference statements; 1 wasm-only macro (`Coalesce`); 53 same-name macros with
  a different body; 33 desktop macros with no browser counterpart; 73 names where the browser
  runs a native namesake of a desktop macro; 2 app bundles differ from the reference.
- Tier A CQL: 1,818 GREEN, 126 PARITY_GAP, 60 ENGINE_DIFF, 6 BOTH_FAIL, 22 translate errors.
- Tier A ViewDefinition 144/144 and OMOP 38/38 GREEN.
- Real engine, whole CQL corpus: 1,809 GREEN, 137 PARITY_GAP, 58 ENGINE_DIFF. The 14 real-only
  cases are all the **stale shipped wasm bundle** (precision-stepped successor/predecessor,
  Quantity `div` unit cancellation, the AMUX-171 Time rules).
- Staleness list (x86 bundles provide, shipped wasm lacks): `comparable`,
  `cql_equivalent_in_valueset`, `fhirpath_equivalent_in_valueset`, `roundquantity`,
  `roundquantityto`.
- Four reference macros are **broken everywhere**, simulator included: `AllTrue`, `AnyTrue`,
  `AllFalse`, `AnyFalse` call `system.bool_and(list)` / `bool_or(list)`, overloads no DuckDB
  1.5.x has (Binder Error).
