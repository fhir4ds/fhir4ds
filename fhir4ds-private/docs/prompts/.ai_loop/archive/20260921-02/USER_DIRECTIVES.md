# 🎯 USER DIRECTIVES — OPERATIONS LAYER + CLI/MCP ADAPTERS

<!--
This file is the PRIMARY MANDATE for the AI Initializer for the operations-
layer groundwork cycle. The v0.0.16 CQL Type System pipeline completed
2026-09-21 (archived at archive/20260921-01/) — this cycle builds on the
post-0.0.16 tree. Design inputs: docs/architecture/plans/
FEATURE_AGENTIC_VERIFY_MCP.md and FEATURE_CQL_STUDIO_LITE.md (§2a).
-->

## Strategic Goal

Lay the **shared operations layer** groundwork from FEATURE_CQL_STUDIO_LITE.md
§2a (capability model) and build the first two thin adapters on it — the
**`fhir4ds verify` CLI** and the **`fhir4ds-mcp` stdio server** — per
FEATURE_AGENTIC_VERIFY_MCP.md.

Capabilities are defined **once** in the operations layer as typed, versioned
envelopes (`schema: 1`); CLI and MCP are thin adapters; parity is enforced by
a **capability-matrix test** (same fixture through CLI subprocess and
in-process MCP client, identical envelopes modulo transport framing). The
studio leg of the matrix is added later without changing the fixture.

**The operations layer is NOT pre-specced here.** Its architecture is the
feature design's primary deliverable (see FDD deliverables checklist).

## Framing

Groundwork cycle — **no version bump**. Pipeline stops after code_review (no
pre_release / docs_audit / scribe); new modules (`fhir4ds/operations/`,
`fhir4ds/mcp/`, `fhir4ds/cli/verify.py`) ship in the next versioned release
cycle.

## Pipeline

1. `feature_design`
2. `feature_implementation`
3. `code_review`

## Scope — v1 capability cut (7 capabilities)

| # | Capability | CLI | MCP |
|---|------------|-----|-----|
| 1 | parse/validate CQL | (via verify diagnostics) | `parse_cql` |
| 2 | emit SQL | `verify --emit-sql` | `translate_cql` |
| 3 | evaluate populations | `verify` | `evaluate_library` |
| 4 | run test cases | `verify --tests` | `run_tests` |
| 5 | FHIRPath eval | — | `fhirpath_eval` |
| 6 | dataset load + stats | (via verify --data) | `load_dataset` |
| 7 | evidence / explain | — (data layer only) | `explain_patient` |

**Deferred (do not build here):** `compare_evidence` + `explain --baseline`
deltas, `validate_resource` / `resource_schema` (resource pair), the static
HTML evidence report (verify FDD deliverable 3 — only the evidence JSON
structures it would consume), the studio (own FDD later), HTTP transport,
remote datasets.

## Feature Design

Execute `ROLE_FEATURE_DESIGNER.md`. The WAIT_FOR_USER_APPROVAL gate is
**KEPT**: the refined FDD gets a human review (Joel) before implementation.
Use `/second-opinion` on the operations-layer architecture during design
refinement and present its view alongside the designer's.

### Problem statement

Both FDDs reference a shared operations layer, but **neither specifies it**:
no module layout, no envelope dataclasses, no error taxonomy, no
connection/dataset injection model. The diagnostics surface (`diagnostics:
[...]`) — the field agents actually consume for self-correction — is
underspecified: without a stable machine-readable code list, each adapter
will invent its own strings. This design produces the missing contract; the
two FDDs become consumers of it.

### Design inputs

- `docs/architecture/plans/FEATURE_AGENTIC_VERIFY_MCP.md` (CLI + MCP
  surfaces, verify envelope sketch, test-case schema §7, D1–D4 decisions)
- `docs/architecture/plans/FEATURE_CQL_STUDIO_LITE.md` §2a (capability
  model, parity matrix, surface-only-conveniences rule)
- Existing surfaces the design must research, not reinvent:
  `fhir4ds/cli/` (main.py structure rules, dqm.py patterns, exit-code and
  stdout conventions), `evaluate_measure` + `audit_mode="full"` evidence
  shapes, `FHIRDataLoader`, `fhir4ds/cql/fhir_server/` facade envelopes
  (CQLTypeRef / result serializer — the 0.0.16 metadata-first surface),
  `fhir4ds/sqlquery/` runner (typed error hierarchy precedent).

### Design constraints (binding)

1. **Adapter-only.** No translator / evaluator / loader semantic changes.
   The operations layer orchestrates existing public APIs (`parse_cql`,
   `translate_library_to_sql`, `evaluate_measure`, `FHIRDataLoader`, the
   audit engine) — zero new engine code paths.
2. **Operations layer is engine-orchestration only.** No session state, no
   argv parsing, no process lifecycle in the core: operations take a
   connection + dataset spec and return envelopes. MCP dataset handles
   (D2) and CLI parsing live in the adapters. The designer may push back
   at the approval gate with concrete evidence if research says otherwise.
3. **Typed, versioned envelopes (`schema: 1`)** shared by all surfaces;
   envelope changes bump `schema` so adapters and agents can detect
   incompatibility.
4. **Typed diagnostics taxonomy.** Stable machine-readable codes (parse /
   translate / evaluation / timeout / input, refined by the designer)
   mapped from the existing typed Python error hierarchy — never
   free-form strings, never tracebacks at an adapter boundary.
5. **`mcp` SDK behind an optional `[mcp]` extra**; entry point
   `fhir4ds-mcp` in `[project.scripts]`; stdio transport only; zero new
   required dependencies.
6. **Test-case schema** (verify FDD §7) lands as a shared operations input,
   `"schema": 1` versioned; unknown patient / unknown define → case
   failure with reason, not crash.
7. **CLI conventions per AGENTS.md**: exit codes 0 (all pass) / 1 (failing
   cases or validation errors) / 2 (invalid CLI input); stdout is the
   contract under `--format json`; argv map to the same dataclasses as the
   Python API.
8. **Studio-compatibility consideration** (non-binding): where cheap,
   prefer operation inputs that a browser worker can supply later (e.g.
   dataset spec accepts inline `resources[]` AND file paths; the MCP
   inline-payload cap from verify FDD risk #2).

### FDD deliverables checklist

- Operations module layout (`fhir4ds/operations/`) + envelope and
  diagnostics dataclasses (single source of truth — REV-002 family rule).
- Per-capability operation signatures for the 7 v1 capabilities.
- Connection / dataset injection model (per constraint 2).
- Diagnostics taxonomy table: code ↔ typed Python error ↔ adapter
  rendering.
- Capability-matrix test design: fixture set, CLI-subprocess and
  in-process-MCP-client legs, envelope normalization rules.
- How the two existing FDDs are updated to consumers of the contract
  (surgical edits or a short annex — designer's choice).
- Rollback / compatibility notes (new modules are additive; no engine
  surface changes to revert).

## Acceptance Gates (binding for implementation)

1. **Master conformance gate**: 2832/2832 (ViewDef 144, FHIRPath 935,
   CQL 1706, DQM 47) — untouched, hard, non-negotiable.
2. **Full pytest trees green** (`fhir4ds/cli`, `fhir4ds/cql`,
   `fhir4ds/dqm`, `fhir4ds/sources`, `fhir4ds/viewdef`) — no regressions;
   include the 0.0.16 type-map tripwires in the spot-check set.
3. **Capability-matrix test green**: identical envelopes across CLI and
   MCP on the shared fixture.
4. **Typed diagnostics on malformed input** in both adapters (bad CQL, bad
   JSON, missing files, unknown defines) — never tracebacks; CLI exit
   codes per convention.
5. **No new required dependencies**; `pip install fhir4ds-v2` unchanged;
   `[mcp]` extra installs and boots the stdio server.
6. **MCP README** client-config snippets (Claude Desktop, opencode,
   Cursor) land with the server.

## Feature Implementation

Per `ROLE_FEATURE_ENGINEER.md`, execute the approved FDD. Surgical diffs;
regression tests land with each unit of work (per-adapter, not one
big-bang suite). Every checkin-sized unit passes gates 1–3 before the next
starts. Suggested unit ordering (designer may refine): operations core +
envelopes → verify CLI → MCP server → matrix test → README.

## Code Review

Standard `ROLE_CODE_REVIEWER.md` audit of the full campaign diff. Verify:
adapter-only invariant (no engine-module diffs), no duplicated
envelopes/taxonomy tables (REV-002 family), envelope `schema` versioning
present, clobber spot-checks for the 0.0.16 type-map symbols
(`TypeMapBuilder`, `cql_type_ref`, tripwire test) still intact, extension
binaries untouched (md5 parity — flag ANY binary change as a finding),
diagnostics taxonomy actually used at both adapter boundaries.

## Focus Areas (cross-cutting)

- **No commits** at any pipeline step — Joel reviews and commits.
- **Single-writer discipline**; the uncommitted
  `extensions/cql/src/cql_extension.cpp` diff
  (`cqlDateTimeEqualListElement`, dual-engine tested in the 0.0.16
  release) is awaiting Joel's commit — do not touch or revert it; this
  campaign must not require extension rebuilds.
- **PROC_VALIDATION.md context rules** (PYTHONPATH=/mnt/d/fhir4ds,
  filtered output, fresh runs).
- **Non-regression**: gates 1–2 run per implementation unit AND at
  code_review.
- **Fix root causes**; no heuristic shims over the envelope contract.
- **Deferred, do not do here**: HTML evidence report, delta/baseline
  comparisons, `compare_evidence`, `validate_resource` /
  `resource_schema`, studio, HTTP transport, remote datasets, version bump
  and release steps.
