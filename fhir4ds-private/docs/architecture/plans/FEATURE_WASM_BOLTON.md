# FDD — c-wasm-bolton: The WASM App Becomes THE Cleanroom Product

**Status**: ROLE_FEATURE_DESIGNER draft v1 — awaiting conductor review + Muse design gate
**Author**: opencode-fix4 (campaign c-wasm-bolton, 2026-10-13)
**Baseline**: dev @ cf66ab1d (committed + pushed; safe rollback point)
**Directive**: user-directed DIRECTION REVERSAL — the WASM app becomes THE cleanroom product.

---

## 1. Problem / Opportunity

Today there are two UIs:

| | dev-server UI (`web/dev-server/`) | wasm-demo (`web/wasm-demo/`) |
|---|---|---|
| Engine | Python server (DuckDB native, full CQL/DQM stack) | In-browser (DuckDB-WASM + Pyodide translation) |
| Surfaces | Full cleanroom: cells, datasets, measures, expected results, MADiE import, terminology, run history, evidence, builder | Playground: single-buffer editor, SQL out, CMS viewer, SMART, SDC, Builder |
| Distribution | `fhir4ds dev` (local python) | Static hosting (website, embeds) |
| Data | Real local workspaces (watcher, kernel restart) | Uploaded/inline only |

Users get the full cleanroom only through the python-served UI, which
duplicates component maintenance (dev-server App.tsx 1,458 lines vs wasm
569, plus 15 pane components) while the wasm app — the public-facing
surface — lacks the cleanroom workflow. The bolton campaign makes the wasm
app THE product: one UI, two engines, progressive enhancement.

## 2. Product Direction (locked by conductor)

1. **Python app startup**: `fhir4ds dev` serves the WASM build + handshake
   (standalone/embed mode preserved).
2. **Local files** via server-mediated workspace APIs (file tree, add-path,
   watcher/reload in the wasm nav).
3. **Cell-based editor/execution** ported into the wasm CQLEditor surface
   (markers, refs_of dep closure, per-cell runs, inline results;
   ServerTransport when connected, in-browser fallback).
4. **Terminology** (VSAC/UMLS/FHIR) import + status wired to existing
   endpoints.
5. **Architecture**: ServerTransport implements the engine seam; progressive
   enhancement; the dev-server UI shell RETIRES at arc end (binary + API
   remain).

## 3. Current Architecture Facts (recon from cf66ab1d)

### 3.1 The Transport seam already exists — and is the load-bearing asset

- `web/dev-server/src/transport.ts` (547 lines): the complete
  `Transport` interface — `health`, `workspace`, `defineTypes`,
  `library`, `translate`, `evaluate`, `verify`, `explain`,
  `runCell/syncCells/onCellEvent`, `runsList/runSqlGet/runsClear`,
  `restartKernel`, `onWorkspaceEvent`, `dataset/viewRun`,
  terminology suite (`terminologyPreview/Import/Resolution/Search/ConfigGet/ConfigPost`),
  `fsList`, `workspaceAddPath`, MADiE importers, S3b expected-results
  (`testsExpectedGet/Save/Delete/Capture/Run`), `schemaTree`,
  `resourceValidate/Save`, `patients`, `valueset*`, `parameters`,
  measure suite (`measureScaffold/Run/Compare/Baseline*`).
- `web/dev-server/src/http-transport.ts` (458 lines):
  `HttpTransport implements Transport` — thin fetch wrappers +
  WebSocket `/api/events` fan-out (workspace events + cell events).
- `web/dev-server/src/wasm-transport.ts` (15 lines): skeletal
  compile-time fixture PROVING the seam is engine-agnostic ("the
  interface can be implemented without HTTP").
- `web/dev-server/src/cells.ts` (107) + `boxes.ts`: client cell/box
  logic; server twin `fhir4ds/devserver/cells.py`
  (`split_boxes`, `rename_box`, `dependency_closure` :217,
  `CellSessionRegistry` :471).
- The dev-server UI already reuses wasm-demo components via the
  `@wasm-demo` vite alias. The dependency direction is
  dev-server → wasm-demo. **The bolton reverses who owns the shell.**

### 3.2 Server static serving is minimal

`api.py _serve_static` serves only `/` and `/assets/*` from the
committed `fhir4ds/devserver/static/` build. The wasm app build
(vite, hash-named assets) drops into this shape, but the handshake
(who am I talking to? connected or standalone?) does not exist yet.

### 3.3 WASM engine surface (in-browser fallback)

- `usePyodide` — CQL translation via micropip
  (`wheel, deps=False` + antlr4-runtime + python-dateutil; never duckdb).
- `useDuckDB` — DuckDB-WASM execution (rescales DECIMAL via schema
  typeId 7 + scale); `cql-macros.ts` carries the 4 BENCH-001
  disambiguation macros.
- `CQLEditor.tsx` — a 34-line plain Monaco wrapper (`language="sql"`),
  no cell support. The playground evaluates whole-buffer.

### 3.4 Server-side capabilities the wasm app will reach

- Kernel/KernelManager (mixed ndjson+bundle boot FIXED by hotfix
  ad936db7 — merge before/with this campaign; slice 1 touches the same
  surfaces), watcher (changed vs data-hint; locked decision 4: data
  changes never auto-reload), runlog store, expected_store,
  madie_import, terminology settings (VSAC/UMLS endpoints exist:
  terminologyPreview/Import/Resolution/Search + configGet/Post).
- `fhir4ds/cli/dev.py` — startup entry (dir, --port, repeatable
  *-dir adds, --no-open).

## 4. Design

### 4.1 Mode model: ONE app, THREE modes

| Mode | How entered | Engine | Data |
|---|---|---|---|
| **standalone** | Static hosting (website, `/wasm-app/`), no server | In-browser (Pyodide translate + DuckDB-WASM run) | Uploaded/inline only (today's behavior, preserved) |
| **connected** | Served by `fhir4ds dev` (or pointed at a server via settings) | Server (native DuckDB, full CQL/DQM) | Real local workspace via server APIs |
| **embed** | `<fhir4ds-view>` web component on a host page | Per host: standalone by default; connected if host supplies a server URL | Per mode |

**Handshake**: on boot the app fetches `/api/mode` (new endpoint).
- 200 + `{server: true, version, workspace}` → connected mode; mount
  `ServerTransport`.
- fetch failure / 404 → standalone; mount `BrowserTransport`.
- Web component attribute `server-url` overrides (embed-connected).
The handshake is a pure additive API — the existing `/health` stays.

**Progressive enhancement contract**: every capability degrades
gracefully along the matrix in §4.4; connected-only capabilities
render as visible-but-disabled with a "requires a connected server"
 affordance, never as errors.

### 4.2 Transport contract (the engine seam)

Move `transport.ts` + `http-transport.ts` into the wasm package
(`web/wasm-demo/src/transport/`), leaving re-export shims in
dev-server for the transition. Then:

- `ServerTransport` = the existing `HttpTransport` (renamed for the
  product vocabulary) — already implements the full Transport seam
  incl. WebSocket events.
- `BrowserTransport implements Transport` — REAL implementation this
  time (the fixture grows up): in-browser engine backing the same
  interface for the standalone surface subset (see matrix). It composes
  `usePyodide`-equivalent translation and DuckDB-WASM execution behind
  Transport method shapes, so the UI never branches on engine identity
  — only on capability availability.
- Capability discovery is mode-driven: `Transport.capabilities():
  Capabilities` (new, additive method) returns a set (e.g.
  `{"translate", "evaluate", "cells", "datasets", "terminology",
  "measures", "expected", "madie", "fs"}`). UI gates on it.

### 4.3 Surface mapping (dev-server → wasm app)

| dev-server surface | wasm target | Port action |
|---|---|---|
| App shell (icon rail + slide-outs, 1,458 lines) | `WorkspaceLayout` + new `CleanroomShell` | Rebuild as wasm-first nav (see §4.6) |
| Cells editor (boxes, markers, per-cell runs, dep closure) | `CQLEditor` grows cell mode | Port client logic (`boxes.ts`, `cells.ts` move to wasm pkg); server runCell/SSE endpoints already exist |
| DatasetPane | new `DatasetPane` in wasm pkg | Move component (server-gated) + keep wasm Builder uploader for standalone |
| ValueSetPane | new `ValueSetPane` in wasm pkg | Move (server-gated); standalone keeps inline VS editor |
| MeasurePane + expected results + baselines | new `MeasuresPane` | Move (server-only; hidden standalone) |
| TestsPane (S3b capture/run/compare) | part of `MeasuresPane` | Move (server-only) |
| TerminologyDialog | move + extend with UMLS status | Wire to existing endpoints; add UMLS key state |
| RunHistoryPane + runs/sql | move | Server-only; standalone shows session-local history |
| EvidenceModal, PatientSlideOut, ParamsPane, PathPickerDialog | move | Same components both modes where capable |
| ResourceBuilderPane | keep wasm `ResourceBuilder` (it originated there) | Add "save to workspace" action when connected |
| VdPane (views) | move | translate+run in-browser works standalone; dataset-backed views connected |

### 4.4 Standalone vs connected capability matrix

| Capability | standalone | connected |
|---|---|---|
| CQL translate | ✅ in-browser (Pyodide) | ✅ server |
| Evaluate single define | ✅ DuckDB-WASM over uploaded/inline data | ✅ server kernel over workspace data |
| Cell editor + per-cell runs | ✅ (in-browser engine; dep closure client-side) | ✅ (server cells API, real dep closure) |
| SQL view (translate output) | ✅ | ✅ + runs/sql sha history |
| Datasets: upload/inline | ✅ (Builder/uploader, today) | ✅ |
| Datasets: local workspace files | ❌ | ✅ fsList/workspaceAddPath/watcher reload |
| Measures (scaffold/run/compare/baselines) | ❌ (hidden) | ✅ |
| Expected results (S3b) | ❌ (hidden) | ✅ |
| MADiE import | ❌ (hidden) | ✅ |
| Terminology VSAC/FHIR import | ❌ (paste-inline only) | ✅ full import + resolution status |
| Terminology UMLS | ❌ | ✅ (existing UMLS endpoints + key state) |
| Run history | session-local | ✅ persistent runlog |
| Evidence/explain | ❌ (no server) | ✅ |
| SMART / SDC / CMS viewer / Builder | ✅ unchanged | ✅ unchanged |

### 4.5 Slice plan (each slice: implement → Muse gate → next; code review at end per dispatch)

1. **Slice 1 — Serve + handshake (item 1)**
   `fhir4ds dev` serves the wasm build (new static root preference:
   wasm build committed like today's static/, or `--ui wasm|legacy`
   flag with wasm default at arc end); `/api/mode` handshake;
   ServerTransport mounts in the wasm app when connected; standalone +
   embed modes bit-identical to today (regression: existing wasm e2e +
   website embed suite). Dev-server legacy UI still available via
   `--ui legacy` during the arc.
2. **Slice 2 — Workspace files (item 2)**
   File tree nav (fsList), add-path flows per kind, watcher-driven
   reload (`onWorkspaceEvent` → nav badges + data-hint restart
   affordance honoring locked decision 4), dataset pane server-gated.
3. **Slice 3 — Cells (item 3)**
   Port boxes/cells client logic into the wasm package; CQLEditor
   cell mode (markers gutter, per-cell run chips, inline results,
   dep-closure highlighting); runCell over ServerTransport when
   connected; BrowserTransport cell execution in-browser (translate
   whole library via Pyodide + evaluate per-define via DuckDB-WASM,
   dep closure client-side via refs_of port). Dep-closure parity test:
   client closure vs server `dependency_closure` on fixture libraries.
4. **Slice 4 — Terminology (item 4)**
   TerminologyDialog full wiring: VSAC preview/import/resolution,
   FHIR server search, UMLS import + key-configured status display;
   standalone keeps inline ValueSet paste (today's behavior).
5. **Slice 5 — Retirement (arc end)**
   `--ui legacy` removed; dev-server UI shell (App.tsx + panes)
   deleted; binary + API remain; `fhir4ds/devserver/static/` now
   contains the wasm build; website embed regression green; docs
   (README quickstart, website cleanroom page) updated.

### 4.6 UI shell design (Muse gate will review)

- Connected mode adds a **workspace rail** (libraries / datasets /
  valuesets / measures / terminology / history) to the existing
  `WorkspaceLayout`; standalone shows today's playground rail. One
  shell, two rail configs — not two shells.
- Cell mode is a toggle on the editor (monaco decorations for `// # %%`
  markers; run chips per cell header; results inline below each cell;
  dep-closure highlight on hover of a define). The playground's
  whole-buffer Run stays for non-cell buffers.
- Status bar gains: engine badge (`wasm` / `server vX.Y`),
  workspace name, watcher state dot (uses existing StatusDot).

### 4.7 Risks & mitigations

| Risk | Mitigation |
|---|---|
| HttpTransport/WebSocket assumes same-origin | Handshake returns base URL; transport takes explicit base (already ctor param); CORS not needed same-origin; document cross-origin embed = standalone |
| Pyodide wheel size on server-served page | Connected mode NEVER loads Pyodide (ServerTransport); standalone unchanged |
| Cell dep closure parity client vs server | Port `dependency_closure` faithfully (pure function, unit-tested both sides on fixture libs) |
| Loss of dev-server UX during arc | `--ui legacy` escape hatch until Slice 5; both UIs green through the arc |
| static/ build freshness (website doctrine) | Commit builds; slice 1 adds CI check that wasm build hash matches `npm run build` output |
| QA-002 hotfix interleave | Merge hotfix ad936db7 first or with slice 1 (same files: kernel/api surfaces) |

### 4.8 Retirement plan (arc end, Slice 5)

- DELETE: `web/dev-server/src/App.tsx`, all pane components unique to
  it (after their wasm-pkg moves complete), `--ui legacy`.
- KEEP: `fhir4ds/devserver/api.py` (binary+API), cells.py server
  primitives, transport/http-transport (now living in wasm pkg),
  `fhir4ds dev` CLI (now serving wasm build by default).
- The dev-server pytest suite stays green throughout (API tests are
  UI-independent); dev-server e2e migrates to the wasm-app-connected
  mode stepwise per slice (mixeddata.spec.ts etc. port in Slice 5).

## 5. Verification plan (per slice; full gates each slice)

- **Python**: devserver pytest (211 baseline), operations/loader suites.
- **Web**: wasm-demo existing playwright (playground + web-component +
  builder + clinic), NEW per-slice specs (handshake, fs nav, cells,
  terminology), dev-server e2e kept green until Slice 5 migration.
- **Parity**: cell dep-closure client-vs-server; standalone behavior
  unchanged (golden flows); embed website suite.
- **Conformance**: master gate 2832/2832 at arc end (server engine
  untouched, but run to prove it).

## 6. Open questions for conductor / Muse

1. Rail vocabulary in connected mode — mirror dev-server icon rail or
   simplify (Muse)?  Proposal: simplify to 6 items.
2. Should standalone cell execution honor `RunMode` deps modes
   (cell/cell_deps/to_here) identically to server? Proposal: yes —
   same semantics, client-computed closure.
3. UMLS key entry UX in connected mode: env-var-only (server doctrine)
   or settings dialog writes toml? Proposal: env-var display + link,
   no secret writing (security doctrine).
4. Timing of dev-server e2e retirement: per-slice port (proposed) vs
   big-bang in Slice 5?
