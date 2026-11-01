# ARCHITECTURE SELF-AUDIT — Operations Layer + CLI/MCP (design phase)

Auditor: Feature Designer (self-audit per ROLE_FEATURE_DESIGNER step 3)
Scope: FEATURE_PLAN_DRAFT.md v1
Date: 2026-09-21

## Golden Standard — invariants for this design (falsifiable)

- **INV-1 (Adapter-only)**: The campaign diff touches no module under
  `fhir4ds/cql/` (except tests), `fhir4ds/fhirpath/`, `fhir4ds/dqm/`,
  `fhir4ds/viewdef/`, `fhir4ds/sources/`, or `extensions/`. Operations
  may only IMPORT existing public APIs.
- **INV-2 (Single envelope source)**: Envelope/diagnostics shapes are
  defined exactly once (`fhir4ds/operations/envelopes.py`). CLI and MCP
  adapters serialize those dataclasses; neither defines its own response
  schema. (REV-002 drift family.)
- **INV-3 (No session/argv/process state in operations)**: Operations
  functions accept `conn` + value-type inputs and return envelopes; no
  module-level mutable state; no argparse; no stdin/stdout; no signal
  handling in `fhir4ds/operations/`.
- **INV-4 (Typed diagnostics at every boundary)**: Every failure path
  reaching an adapter produces `Diagnostics(code=..., message=...)` from
  the fixed enum — no raw `str(exception)` at adapter boundaries, no
  tracebacks to MCP clients or CLI stdout.
- **INV-5 (Schema versioning)**: Every serialized envelope carries
  `schema: 1`; changing a field without bumping is a contract break.
- **INV-6 (Engine error mapping is total)**: The mapping table in
  `errors.py` assigns a code to every typed engine error the operations
  surface can intercept; unmapped exceptions are a design gap to log,
  not a place for `except Exception: EVALUATION_ERROR` blanket catches.
- **INV-7 (Matrix test defines parity)**: A capability is done only when
  `test_capability_matrix.py` covers it on both legs (CLI subprocess +
  in-process MCP client) with identical normalized envelopes.
- **INV-8 (Optional-dependency isolation)**: `import fhir4ds` and every
  non-MCP surface work with `mcp` absent; `fhir4ds/mcp/` imports are
  lazy/guarded so a missing SDK yields a typed, actionable error.

## Audit of the draft (ruthless pass)

### S1 — PASS with note: envelope base class naming
Using `Envelope` as a frozen dataclass base with capability payloads
"extending" it needs care: frozen dataclass inheritance re-declares
fields. Resolution: make `envelopes.py` define concrete result dataclasses
each carrying `schema`/`ok`/`diagnostics` via a shared mixin or
composition rather than deep inheritance. Refined in v2 (§3.2).

### S2 — PASS: layering
Operations import engine APIs only; adapters import operations only;
no adapter imports engine modules directly. Verified against the draft
module layout — one risk: `explain_patient` reaching into
`fhir4ds/dqm/evaluator.py` internals. Refined in v2: route through the
documented `evaluate_measure(..., audit_mode="full")` + audit result
shape, not private attributes.

### S3 — FLAG (MEDIUM): timeout semantics underspecified
Draft lists `--timeout-seconds` and a `TIMEOUT` code but the draft does
not say WHERE the guard runs. Options: (a) adapter-level signal alarm —
Unix-only, risky with DuckDB; (b) operations-level cooperative check —
engine has no cancellation hooks; (c) CLI-only watchdog process —
complex. v2 resolution: **v1 ships the flag as CLI-input validation +
best-effort wall-clock reporting in `timing_ms`, and TIMEOUT code is
reserved (never emitted) in operations core**; document honestly in the
FDD as a v1.1 hardening item. No fake cancellation.

### S4 — FLAG (LOW): dataset handle lifetime
MCP handle map can hold references to loaded tables after the client
changes datasets. v2 resolution: `load_dataset` on an existing handle
idempotently replaces (same-name table overwrite semantics already in
FHIRDataLoader); handles are string ids in a plain dict — no resource
leak beyond the process lifetime; document single-connection doctrine
(D2).

### S5 — FLAG (LOW): `translate_cql` include resolution
`LibraryText` list shifts include resolution to the CALLER (agent must
send FHIRHelpers text every call). That is correct for stateless parity
(CLI `--include-dir` resolves from disk), but MCP ergonomics suffer.
v2 resolution: operations accept BOTH inline `libs[]` AND the CLI keeps
`--include-dir`; the MCP adapter may cache include texts it has seen in
the session (adapter-level cache, not operations state) — parity
contract covers envelope shape, not transport-side caching. Documented
as a surface-only convenience per §2a rules.

### S6 — PASS: exit codes / stdout contract
Matches CLI AGENTS.md exactly (0/1/2; JSON only when promised).

### S7 — FLAG (MEDIUM): diagnostics stability vs engine error drift
Typed-error → code mapping depends on engine exception types that the
campaign must not modify (INV-1). If the engine introduces a new typed
error later, mapping misses it. v2 resolution: mapping is total over
CURRENT engine errors + a last-resort `EVALUATION_ERROR` with the
original type name embedded in `detail` (not `message`) — codes remain
stable strings even when engine types evolve. Add matrix leg asserting
diagnostics equality.

### S8 — PASS: test-case schema §7
Unknown patient/define → case failure with reason (not crash) is already
the draft behavior; v2 adds `reason` field shape to the failure payload.

## Verdict

Draft is architecturally sound after the S1/S3/S5/S7 refinements.
Proceed to v2 refinement incorporating all four.
