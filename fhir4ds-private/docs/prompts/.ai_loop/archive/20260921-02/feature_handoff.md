# Feature Handoff — Operations Layer + verify CLI + MCP Server

**Date:** 2026-09-21
**Workflow:** feature_implementation (pipeline step 1)
**FDD:** `docs/architecture/plans/FEATURE_OPERATIONS_LAYER.md` (v3.2, approved)

## What was built

All 7 v1 capabilities + both adapters + parity test + website docs:

- **`fhir4ds/operations/`** — envelopes (`schema: 1`, `ok`/`passed`,
  Diagnostics with code/severity/location/data), total error mapping
  (8 codes; `TIMEOUT` reserved never-emitted), DatasetSpec/TestsInput
  strict parsing, §3.3.1 library resolution chain (inline → bundled
  `importlib.resources` → adapter extras → typed NOT_FOUND; explicit
  beats implicit), capabilities: parse (declarations metadata for
  editor surfaces), translate, fhirpath_eval, load_dataset,
  evaluate_library (rows + column_types + opt-in sql),
  run_tests (evaluate-once; unknown patient/define → case failure with
  reason), explain_patient (patient_ids pushdown; audit-dict
  `{result, evidence}` unwrapping).
- **`fhir4ds/cli/verify.py`** — `fhir4ds verify` (registered in
  main.py); argv → dataclasses → operations → stdout JSON; exit codes
  0/1/2; derived `summary` for the no-cases path (parity with
  run_tests); `--format text` human mode; `--emit-sql`.
- **`fhir4ds/mcp/server.py`** — FastMCP stdio server; 7 tools mapping
  1:1 onto operations; `build_server()` test seam; adapter-owned:
  single DuckDB connection (async-lock discipline via tool-manager
  serialization), dataset handle map (single-active-dataset; stale
  handle → typed not_found), session include cache (explicit wins),
  5MB inline payload cap with NDJSON remediation message, stdout→stderr
  redirect at boot. `[mcp]` extra + `fhir4ds-mcp` entry point in
  pyproject (core install unchanged).
- **Capability-matrix test** — CLI subprocess vs in-process MCP client
  on the shared fixture (library with bundled-FHIRHelpers include, 3
  patients, 4 cases incl. unknown-patient): identical normalized
  envelopes.
- **Website Interfaces pages** — `user-guide/interfaces/{operations,cli,mcp}`;
  cli.md absorbed into the category with the verify reference; sidebar
  restructured; inbound links fixed; typecheck + build green.

## Verification

- New tests: 64 passed (23 envelopes/errors/resolver, 16 capabilities,
  7 CLI, 10 MCP, 1 matrix, + fixtures module). MCP tests skip cleanly
  without the optional SDK.
- Full pytest trees: cli/cql/dqm/sources/viewdef green (background run
  recorded).
- Master conformance gate 2832/2832 (background run recorded).
- Adapter-only invariant verified via git status: only `cli/main.py`
  (dispatch entry) + `pyproject.toml` (`[mcp]` extra + script) modified;
  all other tracked diffs (AGENTS.md, cql_extension.cpp, clangd caches,
  conformance report) are Joel's pre-existing 0.0.16 work, untouched.
- Website: 4 pre-existing api-reference broken links reproduce at git
  HEAD (verified via worktree build) — NOT this campaign; `onBrokenLinks:
  'warn'` per site config.

## Design deviations from FDD

None of substance. Implementation notes:

- frozen-dataclass mixin required re-declaring base fields per result
  class (mixin class attributes are not dataclass fields) — mechanical,
  documented in AGENTS.md.
- `evaluate_measure` is path-based; inline libraries materialize to a
  temp dir inside `_evaluate` (bundled includes also written there so
  include_paths sees one source). No engine change.
- MCP async lock: FastMCP's tool manager serializes handler execution
  per the single-connection doctrine; explicit lock noted for the
  studio-era revisit.

## Known limitations (documented in FDD)

- `TIMEOUT` reserved (no cancellation); `--timeout-seconds` = input
  validation + `timing_ms` reporting.
- Single active dataset per MCP process; multi-dataset isolation
  deferred (documented on the MCP page).
- Streaming/Arrow rows deferred (v1.1 transport concern).

Ready for code_review.
