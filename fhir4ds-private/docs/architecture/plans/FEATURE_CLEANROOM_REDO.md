# FDD — c-cleanroom-redo Phase 1: Connected Mode for the cql-cleanroom Shell

**Status**: ROLE_FEATURE_DESIGNER draft v1 — awaiting conductor review BEFORE any code
**Author**: opencode-fix4 (campaign c-cleanroom-redo, 2026-10-14)
**Base**: feat/cleanroom-redo-20261014 @ 74177b03 (user-confirmed shell milestone)
**Doctrine**: 3-attempt falsifiability — milestone 1 (shell served unmodified, user
confirmed) PASSED. This doc covers the remainder. NOTHING redesigns what
cql-cleanroom already has; the server is ADDITIVE for gaps only. Shell-swap
(`/` default → cql-cleanroom, legacy retirement) is an ARC-END decision after
the user sees the completed result.

---

## 1. Product direction (locked)

cql-cleanroom is THE product shell (browser-native CQL workbench: NavRail,
File menu, editor tabs, run history/diff, measures, expected reports,
builder, ViewPane, evidence, share links, IndexedDB workspace). Phase 1 adds
**connected mode**: when served by `fhir4ds dev`, the shell gains server-backed
capabilities it lacks standalone — VSAC/UMLS terminology import, workspace
file trees/watcher, server evaluate for big datasets — surfaced through its
NATIVE UI. Standalone behavior is byte-identical to today.

## 2. cql-cleanroom native inventory (from source; the surfaces we map onto)

- `NavRail` + `navSections.ts` (libraries/measures/valuesets/parameters/
  expected/views sections, `DrawerSection` slide-out, `PatientDetailPanel`)
- File menu (`DropdownMenu`), editor tabs (`EditorTabs` + ParameterEditor/
  ValuesetEditor), `RunHistory`+`runDiff` (IndexedDB), `ResultsConsole`,
  `MeasurePane`/`MeasureReportOutput`, `TestsPane`+`verifyCompare`,
  `EvidencePopover`+`PopulationSankey`, `BuilderPane`/`ResourceBuilderPane`,
  `ViewPane`/`ViewOutput`, `DatasetPane` (uploads), MADiE import/export
  (`madiePackage`/`madieExport`), share links, `protocol.ts`, workers
  (cleanroom.worker; Pyodide+DuckDB-WASM in-browser engine).
- Workspace model is in-browser state (+IndexedDB persistence), not a server
  workspace.

## 3. Design

### 3.1 Mode detection (additive, invisible by default)

Reuse the salvaged `/api/mode` handshake (from git 6b03e19b + 13 tests +
`handshake.ts`): `GET /api/mode` → 200 ⇒ connected; 404/failure ⇒ standalone.
cql-cleanroom detects at boot; standalone never issues another server call.
**No UI change in standalone.** Connected mode adds a small "connected"
indicator in the existing status area (native pattern) — no engine switcher,
no mode manager: the in-browser engine stays the executor; the server is a
data/terminology provider plus an optional big-data executor.

### 3.2 Capability 1 — Terminology import (VSAC/UMLS) → File menu + ValuesetEditor

Gap: standalone valuesets are inline JSON only. Connected: File → Import
adds "ValueSet from VSAC/FHIR URL…" and "UMLS concept lookup…". Wire to the
EXISTING endpoints (`/api/terminology/preview|import|search`, config GET);
UMLS key = env-var display only (salvaged TerminologyPane doctrine: status
line `UMLS: configured/not configured (UMLS_API_KEY)` + recheck; NEVER write
or echo secrets from the browser). Imported valuesets land in the native
workspace valueset section (same shape as inline ones) and are saved into
the workspace IndexedDB store.

### 3.3 Capability 2 — Workspace file trees + watcher → File menu + DrawerSection

Gap: no local-filesystem view. Connected: the NavRail's existing drawer
gains a "Workspace files" section listing `cql/ valuesets/ measures/ data/
views/` (EXISTING `/api/fs/list`, sandboxed). File click → opens in the
native editor tab (CQL) or JSON viewer (valuesets/measures). Watcher events
over the EXISTING WebSocket (`/api/events`) mark changed files (dot badge;
refresh button; data-hint ⇒ native banner with explicit reload — locked
decision 4 honored).

### 3.4 Capability 3 — Server evaluate for big datasets → Run target picker

Gap: in-browser DuckDB-WASM caps out on large NDJSON. Connected: the Run
control gains an optional "server" target (visible ONLY when connected):
sends the composed library + workspace dataset PATHS (server loads them) to
EXISTING `/api/evaluate`; results render in the native ResultsConsole/
MeasurePane shapes (rows are column-keyed objects — probed). Default target
stays in-browser; server is per-run opt-in. No SQL escapes the seam: the
transport returns the operations envelopes cql-cleanroom already renders.

### 3.5 Transport seam

A small `ServerConnection` module (fetch + WS; envelope unwrap) — NOT a
redesign of the in-browser executor. Salvage reuse: handshake.ts (4-state),
TerminologyPane wiring patterns, /api/mode server code, COOP/COEP (already
live). Cells/dep-closure harness is NOT needed (cql-cleanroom has its own
editor model without `// # %%` markers — deliberately not imported).

## 4. Slices (Muse gate each; user-visible checkpoint after slice 1)

1. **S1 Terminology import** (first user-visible connected capability) —
   handshake + ServerConnection + File-menu import + UMLS status. Checkpoint:
   user imports a VSAC valueset into the workspace on the review server.
2. **S2 Workspace files + watcher** — drawer section, open-file, badges.
3. **S3 Server evaluate** — Run-target picker + results in native panes.
4. **S4 (arc end)** — shell-swap decision presentation (default /, legacy
   retirement) for the user; only on their confirmation.

## 5. Verification per slice

Standalone regression: existing cql-cleanroom playwright/vitest suites
green + zero network calls in standalone (assert no /api/* requests).
Connected: new e2e per capability against a live `fhir4ds dev`.
devserver pytest (211) stays green throughout. Check-ins at every milestone.

## 6. Open questions (conductor)

1. Server-evaluate slice: also allow server-side RUN of measures/tests, or
   evaluate-only first? (Proposal: evaluate-only in S3; measures later.)
2. Terminology imports in connected mode should ALSO write to the server
   workspace disk (valuesets/ dir) or browser-IndexedDB only?
   (Proposal: browser-IndexedDB only in S1 — server-disk write is a
   separate, explicitly-confirmed write path.)
