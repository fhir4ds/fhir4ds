# Code Review Findings — Operations Layer + CLI/MCP Campaign

Date: 2026-09-21
Role: code_review (ROLE_CODE_REVIEWER.md)
Scope: full campaign diff — new `fhir4ds/operations/` (10 modules),
`fhir4ds/mcp/` (2), `fhir4ds/cli/verify.py`, `cli/main.py` dispatch,
`pyproject.toml` (`[mcp]` extra + `fhir4ds-mcp` script), website
Interfaces pages + sidebar, 3 test files + fixtures. ~2,400 lines.

## Verdict: CLEAN_WITH_NOTES

No CRITICAL or HIGH findings remain after in-review fixes. Three issues
were found and FIXED during this review (logged below as resolved);
two LOW notes carried.

## In-review fixes (found by this audit, fixed and re-verified)

1. **REV-022 (HIGH, RESOLVED): MCP dataset handle never advanced.**
   `load_dataset_tool` computed the new handle from a `handles` list key
   that never existed, so every load returned `ds-1`; after a reload,
   stale references to `ds-1` silently matched the NEW dataset (the
   stale-handle `not_found` path was unreachable), and the
   `dict | b if c else b` precedence made the ok-branch shape differ
   from intent. Fixed: monotonic `handle_seq`; each successful load
   issues a fresh handle; prior handles are invalid (server.py).
2. **REV-023 (MEDIUM, RESOLVED): `--timeout-seconds` was inert.** The
   flag was parsed but never validated or reported (FDD §3.6: input
   validation + wall-clock reporting). Fixed: non-positive → exit 2;
   budget echoed as `timeout_seconds` in the CLI envelope
   (verify.py). Matrix normalization updated to drop the CLI-only echo.
3. **REV-024 (LOW, RESOLVED): dead `_spec_is_valueset_only` helper and
   dead `loaded_any`/`verbose_sql`/`column_types` assignments left by
   iterative edits. Deleted (ruff F841 clean; behavior identical).

## Audit results by dimension

- **SQL injection: CLEAN.** No f-string SQL construction anywhere in
  the new surface (grep-verified); the only `conn.execute` is the
  static `SELECT resourceType, COUNT(*) ...` aggregate. All data flows
  through `FHIRDataLoader` (parameterized/quoted per its doctrine).
  Temp-dir library materialization uses `tempfile.TemporaryDirectory`
  and library names validated non-empty (no traversal concern on
  generated filenames; names come from the caller's own include list —
  worst case is a file inside the ephemeral temp dir).
- **Model knowledge in logic: CLEAN.** No FHIR resource/profile/measure
  strings in generic paths; the bundled-library list
  (`FHIRHelpers/QICoreCommon/Status`) is package-content enumeration,
  not clinical behavior.
- **Error hygiene: CLEAN.** Every `except Exception` site converts to
  typed Diagnostics via the total mapping (never `pass`); adapter
  boundaries never leak tracebacks (CLI converts; MCP `_ToolError`
  carries diagnostics payloads). Blanket catches are the documented
  total-mapping last resort with type names in `detail`.
- **Type safety: ADEQUATE.** Frozen dataclasses with `__post_init__`
  validation on all adapter-supplied inputs; strict `*_from_dict`
  parsers reject unknown keys.
- **Redundant parsing: CLEAN.** Parse caches: bundled libraries
  (process), resolver inline ASTs, MCP include cache.
- **Envelope contract: VERIFIED.** `schema: 1` everywhere; `ok` vs
  `passed` semantics consistent across CLI/MCP; matrix test green
  after the timeout echo normalization (CLI-only input echoes are
  documented as out of the parity contract).

## Verification

- 64/64 new tests green (operations 40 incl. matrix, CLI 14, MCP 10).
- ruff clean on all new/modified Python.
- Full trees re-run post-fixes: cli/dqm/sources/viewdef 1673 passed,
  2 skipped; cql 5020 passed, 5 skipped; test_version 2/2.
- Conformance (foreground, final tree): **2832/2832** (ViewDef 144,
  FHIRPath 935, CQL 1706, DQM 47).
- Website: tsc clean, build SUCCESS; campaign links green; the 4
  api-reference broken links reproduce at git HEAD (pre-existing,
  worktree-verified) — not this diff.
- Adapter-only invariant: only `cli/main.py` + `pyproject.toml`
  modified outside new modules and website docs (git status verified).
  No engine modules, no extension binaries touched (md5-relevant
  files unchanged).

## Carried notes (LOW, no action)

- **REV-025 (LOW):** `_audit_definitions` in evaluate.py retains a
  defensive multi-attribute probe for audit evidence on relations; the
  audit evidence currently surfaces through the population-value dicts
  (the `explain_patient` unwrap). If a future audit API lands, prefer
  the documented shape over the probe.
- **REV-026 (LOW):** MCP async-lock discipline relies on FastMCP tool
  manager serialization; an explicit `asyncio.Lock` around
  connection-touching handlers is the FDD's letter — revisit when a
  client actually issues concurrent tool calls (studio era).

## REV ledger

Pre-existing items carried unchanged (REV-002…021 where still open).
New this campaign: REV-022/023/024 (resolved in-review), REV-025/026
(LOW, open notes).
