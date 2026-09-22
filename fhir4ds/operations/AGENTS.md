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
- `operations/capabilities/` — parse, translate (stateless);
  dataset_ops, evaluate, run_tests, explain (conn-taking).
- `mcp/server.py` — FastMCP stdio; `build_server()` is the test seam.
  stdout is redirected to stderr at boot (JSON-RPC owns stdout).
  Single active dataset; stale handles → typed `not_found`. Session
  include cache under caller-supplied libraries (explicit wins).

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
  definition: CLI subprocess vs in-process MCP client on the shared
  fixture. Adapter changes must keep it green; the studio leg extends
  it without changing the fixture.

## Validation

```bash
python3 -m pytest fhir4ds/operations/tests fhir4ds/cli/tests fhir4ds/mcp/tests -q
```

MCP tests skip cleanly when the optional `mcp` package is absent
(`pytest.importorskip`).
