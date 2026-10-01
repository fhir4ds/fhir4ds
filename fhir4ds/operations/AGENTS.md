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
