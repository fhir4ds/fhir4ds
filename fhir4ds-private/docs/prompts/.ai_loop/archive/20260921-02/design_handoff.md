# Design Handoff — Operations Layer + verify CLI + MCP Server

**Date:** 2026-09-21
**Workflow:** feature_design (pipeline step 0)
**Final FDD:** `docs/architecture/plans/FEATURE_OPERATIONS_LAYER.md` (v2 FINAL)
**Draft trail:** `FEATURE_PLAN_DRAFT.md` (v1) + `ARCHITECT_REVIEW.md`
(self-audit, 8 invariants, 4 refinement findings)

## What was designed

The shared operations layer both existing FDDs depend on but neither
specified: `fhir4ds/operations/` with 7 v1 capabilities (parse,
translate, evaluate, run_tests, fhirpath_eval, load_dataset,
explain_patient), typed `schema: 1` envelopes, an 8-code diagnostics
taxonomy totally mapped from engine typed errors, a conn+DatasetSpec
injection model, the `fhir4ds verify` CLI adapter, and the
`fhir4ds-mcp` stdio server (`[mcp]` extra, FastMCP, dataset handle map
owned by the adapter). Parity = capability-matrix test (CLI subprocess
vs in-process MCP client, identical normalized envelopes).

## How it was refined (self-audit findings → v2)

- **S1** frozen-dataclass inheritance hazard → composition/mixin
  envelope fields.
- **S2** `explain_patient` must not touch evaluator privates → routed
  through documented `evaluate_measure(audit_mode="full")` shapes.
- **S3** timeout honesty → `TIMEOUT` code reserved/never emitted in v1;
  `--timeout-seconds` is validation + wall-clock reporting only; no
  fake cancellation around DuckDB.
- **S5** include-resolution ergonomics → CLI `--include-dir` +
  adapter-level MCP include cache (surface-only convenience).
- **S7** diagnostics stability → total mapping with last-resort
  EVALUATION_ERROR + type name in `detail`; codes are the agent
  contract.

## Second opinion

The `/second-opinion` consultation initially failed (no opencode-go
subscription; `opencode` binary absent from PATH). Per Joel's direction
(2026-09-21), re-ran via `opencode run -m fleet-antigravity/agy/
gemini-flash` (Gemini Flash, a different model family than the everyday
glm-5.3 — the point of the consultation). Full 130-line review with
file/line citations archived at
`fhir4ds-private/docs/prompts/.ai_loop/.temp/so_answer_gemini_flash.txt`.

**Findings adjudicated (designer) — accepted, folded into the FDD:**

- **1.1 missing `main` library param** → `main: LibraryText` explicit on
  all multi-library operations (studio worker `mainId` precedent).
- **1.2 dataset ambiguity** → `dataset: DatasetSpec | None = None` on
  evaluation ops (None = use conn's loaded state); idempotent-reload
  rationale documented.
- **1.3 explain_patient O(dataset) cost** → pushdown via
  `evaluate_measure(patient_ids=[id])` (engine already supports it).
- **1.4 DuckDB single-connection concurrency** → async lock serializing
  all connection-touching tool handlers.
- **2.1 dead/unmapped codes** → `SemanticError`→TRANSLATION_ERROR,
  `UnsupportedFeatureError`→UNSUPPORTED_FEATURE, `NOT_FOUND` emitted by
  handle/case resolution; no-dead-code unit test.
- **2.2 unstructured detail** → `Diagnostics.data: dict | None` lifting
  engine structured fields (`expected/found`, `symbol/expected_type/
  actual_type`, `feature_name/workaround`) verbatim.
- **2.3 no severity** → `severity: error|warning|info` on Diagnostics.
- **2.4 ok vs test-passed ambiguity** → `passed: bool | None` field on
  envelopes; CLI exit-1 covers `ok=False` OR `passed=False`.
- **3.1 stdio stdout corruption** → sys.stdout→sys.stderr redirect at
  server boot.
- **3.2 handle-map illusion** → honest single-active-dataset semantics
  (explicit replace + stale-handle NOT_FOUND); multi-dataset isolation
  deferred; documented in README.
- **3.3 cap mechanics/remediation** → cap checked on raw request text;
  error message names the NDJSON-file remediation.
- **4 unit reordering** → U2 = stateless ops (parse/translate/
  fhirpath_eval), U3 = dataset+evaluate, U4 = tests+explain, U1 owns
  the shared matrix fixture.
- **5.1 Pyodide/duckdb-wasm split** → acknowledged boundary in §8:
  stateless ops carry no conn; studio executes SQL in duckdb-wasm
  consuming the same envelope shapes; matrix studio leg adjudicates.
- **5.2 missing inline ValueSets** → `DatasetSpec.valueset_resources`.
- **5.3 core-ten sequencing** → recorded: the deferred resource pair +
  compare_evidence land in a follow-up operations unit BEFORE the
  studio phase needs them (no TypeScript re-implementation).

**Not adopted as-is:** 5.4 (Arrow/columnar rows) — v1.1 adapter
concern; JSON rows are the v1 envelope contract; Arrow changes
transport, not envelopes.

## Binding constraints honored

Adapter-only (INV-1: no engine modules modified); single envelope
source (INV-2); no session/argv/process state in operations core
(INV-3); typed diagnostics at every boundary (INV-4); `schema: 1`
versioning (INV-5); total error mapping (INV-6); matrix test defines
parity (INV-7); optional-dependency isolation (INV-8).

## Gates

Per USER_DIRECTIVES: 2832/2832 conformance untouched; full pytest
trees green; matrix test green; typed diagnostics on malformed input;
no new required dependencies; MCP README configs.

**Post-second-opinion amendment (Joel discussion, 2026-09-21):** §3.3.1
library resolution chain added — includes resolve via inline
`libraries[]` → bundled standards (`importlib.resources` over the
wheel-shipped `fhir4ds/cql/resources/cql/*.cql`, currently dead weight)
→ adapter sources (CLI `--include-dir`, MCP session cache) → typed
`NOT_FOUND` naming the missing alias. Explicit beats implicit: inline
LibraryText overrides bundled same-name libraries. This closes the WASM
import-resolution gap (Pyodide reads wheel resources from the virtual
FS; studio FDD D3 fetching demoted to editor-display concern, Pyodide
verification pinned as a U3 exit criterion). Matrix fixture gains a
no-inline-FHIRHelpers case.

**Post-second-opinion amendment 2 (Joel, 2026-09-21):** §9
documentation plan added — website User Guide gains an **Interfaces**
category (`user-guide/interfaces/{operations,cli,mcp}`) replacing the
flat `user-guide/cli.md`: the operations page documents the capability
model/envelopes/taxonomy/resolution chain as the primary interface doc;
the CLI page absorbs current cli.md + adds `verify`; the MCP page
carries install/tool reference/handles/configs (Claude
Desktop/opencode/Cursor). Gate 6 and U7 updated accordingly.

## Approval gate

Per ROLE_FEATURE_DESIGNER §4 and USER_DIRECTIVES: **WAIT_FOR_USER_APPROVAL.**
Joel must approve the final FDD (`docs/architecture/plans/
FEATURE_OPERATIONS_LAYER.md`) in chat or USER_DIRECTIVES.md before
feature_implementation begins.
