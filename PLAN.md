# S22 Plan (rev 3) — The FHIR-Type Workspace

Status: DRAFT FOR JOEL'S REVIEW — rev 3 folds in AM1–AM8. No
implementation started. Rev 2 → rev 3: the storage layout is now 100%
FHIR resource-type folders at the workspace root (AM5–AM8 supersede the
AM2/AM3 data/ layout); AM1 switcher, Q3/Q5/Q6 answers unchanged.

---

## 1. The workspace convention (AM5 + AM6 + AM7 + AM8)

**The workspace root IS the resource map.** Every top-level directory is
a FHIR resource type (exact FHIR casing); there are ZERO special
directories. One workspace = one directory tree:

```
<workspace>/                          # one workspace = one directory (AM1)
├── Library/                          # AM8: was cql/ — BOTH forms
│   ├── CMS125Demo.cql                #   human-readable CQL (source of truth)
│   ├── CMS125Demo.json               #   FHIR Library resource (ELM/meta), stem-paired
│   └── FHIRHelpers.cql
├── ValueSet/                         # was valuesets/
│   └── <id>.json                     #   one file per ValueSet resource
├── Parameters/
│   └── workspace.json                # shared Parameter defaults (MP, etc.)
├── Patient/                          # SINGLE PATIENT STORE (AM5-3)
│   └── <patientId>/                  #   ONE FOLDER PER PATIENT
│       ├── <patientId>.json          #     the Patient resource
│       ├── Encounter/<id>.json       #     their clinical resources, BY TYPE
│       ├── Procedure/<id>.json
│       └── Observation/<id>.json ...
├── Encounter/<id>.json               # unattributed resources: type folder,
├── Organization/<id>.json            #   one file per resource — same shape
├── Practitioner/<id>.json            #   as attributed ones, no special bucket
├── Measure/                          # MEASURE LAYER — one dir per measure
│   └── <m>/
│       ├── Measure/<name>.json       #   the Measure resource
│       ├── Parameters/overrides.json #   OPTIONAL per-measure overrides
│       ├── List/TestCases.json       #   FHIR List (mode=working) — test-set
│       │                             #     membership BY REFERENCE:
│       │                             #     entry[].item = Reference(Patient/<id>)
│       ├── MeasureReport/<patientId>.json   # expected reports (was expected/)
│       └── ViewDefinition/<name>.json       # was views/
└── _attic/                           # ingest archive (see §3) — ignored
```

### Rules

- **Keys:** patient folder name = `Patient.id`; clinical resource files
  keyed by their own id under their type subfolder. The filesystem is
  the resource-type map at EVERY level; a patient's whole story is one
  browsable folder.
- **Single patient store (AM5-3):** ALL patients live under
  `Patient/<id>/` exactly once — test or general. Test-set membership is
  NOT a storage location; it is a REFERENCE in the measure's
  `List/TestCases.json`. The roster groups by List membership (current
  measure) + "not in any test set".
- **Library pairing (AM8):** a `.cql` and its FHIR Library `.json`
  counterpart share a stem (`Library/CMS125Demo.cql` +
  `Library/CMS125Demo.json`) when both exist. **The `.cql` is the source
  of truth for editing and evaluation; the `.json` carries
  metadata/ELM when present.** Precedence: translation always runs from
  `.cql`; a divergent `.json` shows a badge and is NOT used for
  evaluation; saving from the editor writes the `.cql` (and updates the
  paired `.json` metadata only when the save flow owns it). MADiE
  import lands imported Library resources here alongside extracted
  `.cql`; export serializes from `.cql` (+ the Library resource if
  present).
- **Discovery:** the kernel rglobs over RESOURCE-TYPE FOLDERS ONLY into
  ONE flat `resources` table (CQL retrieves need a single execution
  universe — unchanged semantics from today). The ignore-set: discovery
  descends ONLY into directories whose name is an exact FHIR resource
  type; everything else at the workspace root (`_attic/`, `PLAN.md`,
  dot-dirs, any scratch) is ignored. Inside `Library/`, only `.json`
  Library resources enter the resource table — `.cql` files are source,
  not data.
- **Reserved names:** exact FHIR resource type names (`Patient`,
  `Encounter`, `Organization`, `Practitioner`, `ValueSet`, `Parameters`,
  `Measure`, `MeasureReport`, `List`, `ViewDefinition`, `Library`, …).
  Creating a workspace folder with a reserved name that is not a
  resource type is a typed validation error.
- **Collision guards (ingest-time, typed rejections):** a file under a
  type folder must be a JSON resource whose `resourceType` matches the
  folder; mismatches are rejected with the file path + found/expected
  types. Patient folder name must equal the contained Patient.id.
- **Parameters compose:** resolution at run time = caller-supplied (UI)
  > per-measure `Measure/<m>/Parameters/overrides.json` >
  `Parameters/workspace.json` (extends the S16 merge chain with one
  measure-scoped tier).
- **"Current measure":** explicit picker (Measures drawer), defaulting
  to the active library's owning measure when exactly one measure
  references it; ambiguity falls back to the picker with a badge.

### Technical notes (flagged per AM6/AM7 instruction — not silent deviations)

1. **`Measure/` dual role resolved as: one SUBDIR per measure.** Root
   `Measure/` contains measure directories (`Measure/<m>/`), each
   mirroring the type convention internally; standalone root-level
   `Measure/<id>.json` resources are not a case (a Measure resource
   always belongs to its measure dir). This follows AM5(2) verbatim
   after the AM7 rename.
2. **Legacy `data/` dirs are invisible to the new discovery rule**
   (`data` is not a resource type), so the one-time normalizer (§3) MUST
   run before the first kernel boot in a legacy workspace; its trigger
   is the presence of legacy convention shapes (`data/`, `cql/`,
   `valuesets/`, flat `measures/`, `views/`).
3. **`Library/` is the only mixed-content folder** (source `.cql` +
   resource `.json`); the discovery filter above keeps the two roles
   apart. Its FHIR counterpart relationship is explicit: `.cql` here,
   Library resources here too — same folder, stem pairing, `.cql`
   authoritative (AM8).

## 2. Workspace switcher (AM1)

Multiple workspaces = multiple directories. The devserver roots at the
chosen workspace; the UI gains a **workspace picker** (header + File
menu) listing available workspaces (server mode: a configured workspace
root the devserver scans; standalone: bundled examples + last-opened).

- **The demo becomes a real directory workspace** at
  `examples/demo-workspace/` in this exact convention — kills the ghost
  demo-tab class entirely (Q1 superseded: connected boot = the selected
  workspace's files; no special-cased browser demo state anywhere).
- **Standalone/wasm** boots the demo workspace (or last-opened) from a
  bundled copy shipped in the static build, in memory + IndexedDB.
- **Demo deletable/resettable (AM4b):** deletable like any workspace;
  "Reset demo" restores from the pristine repo copy (server re-copies;
  standalone clears IndexedDB and re-seeds from the bundle).
- Switching reloads app state (fresh kernel boot, fresh drawers);
  unsaved-editor guards fire first.

| Surface | Connected (server workspace) | Standalone/wasm |
|---|---|---|
| Workspace picker | devserver workspace-root scan | bundled examples + IndexedDB |
| Libraries drawer + tabs | `Library/*.cql` via `/api/fs` | memory/IndexedDB copy |
| Valuesets drawer | `ValueSet/` via `/api/fs` | memory/IndexedDB |
| Measures drawer | `Measure/<m>/` dirs | memory/IndexedDB |
| Patient roster | kernel roster + List membership | memory/IndexedDB |
| Expected reports | `Measure/<m>/MeasureReport/` | memory/IndexedDB |
| Run history | IndexedDB (chrome, INV-4) | IndexedDB |
| Editor content | opened from disk via `/api/libraries/<n>` | memory/IndexedDB |

## 3. Normalize-on-ingest → the folder shape (AM2, as superseded by AM5/AM6)

ndjson/bulk formats are **transport only**; the canonical shape is the
tree above.

- **Server-side ingest:** any added `.ndjson`/bulk file is parsed once;
  Patient resources anchor `Patient/<id>/`; resources with a patient
  reference (`subject`/`patient`/`beneficiary`, per the loader's typed
  patient-ref doctrine) land inside that patient's folder under their
  own type subfolder; everything else lands in its ROOT type folder
  (`Organization/<id>.json`, `ValueSet/<id>.json`, …). The monolith is
  archived to `_attic/` (ignored by discovery).
- **Kernel loads ONLY the canonical shape.** The browser never converts
  formats (standalone gets the demo workspace pre-normalized).
- **MADiE test-case imports** land per-patient into the single store;
  test-set membership is written into the measure's
  `List/TestCases.json`.
- **Migration (one-time, first boot):** legacy shapes normalize —
  `data/patients.ndjson` (56 resources / 22 patients) → 22 patient
  folders; `data/patients/<id>.json` bundles (if an AM2-era pass ran)
  split into the folder shape; flat `measures/`, `views/`, `valuesets/`,
  `cql/` remap per §9. Originals archived to `_attic/`.

## 4. Patient roster + editable patients (AM3)

The Tests drawer becomes the **patient roster**:

- One row per `Patient/<id>/` folder: id, name, age (derived), source
  group badge — List membership of the current measure vs "not in any
  test set" — and per-file watcher badges (clinically meaningful:
  "w03 Encounter changed" when `Patient/w03/Encounter/<id>.json` edits
  on disk).
- **Click a patient → their folder opens in the resource editor** — the
  same JSON editor machinery as valuesets (edit + validate + save-back
  to that ONE file via the existing `/api/fs` seam; the patient view
  lists their sub-resources as navigable entries). Kernel hot-reloads
  that patient's rows on save (watcher path).
- Demo patients are editable identically — no special demo concept.
  "Add patient" creates a minimal `Patient/<id>/<id>.json`; delete
  removes the folder (and drops stale List entries with a repair note).

## 5. Export / import — closure over the List (S22d-2)

- **Export ("Save MADiE zip"):** the measure dir contents at MADiE
  paths + the resolved closure of shared dependencies materialized INTO
  the zip: `cql/<Lib>-v<ver>.cql` for the measure library + transitive
  includes (include-graph walk); `resources/valueset-*.json` for the
  closure's valueset URLs; **List-referenced patient folders**
  (test cases) with expected MeasureReports re-attached as trailing
  entries (MADiE zip shape); the measure's Parameters overrides; S18
  extras under `resources/extras/` unchanged. General patients NOT in
  the List are NOT exported.
- **Import ("Open MADiE zip"):** measure files land under
  `Measure/<m>/`; patients land in the single store
  (`Patient/<id>/`); libraries land in `Library/` (extracted `.cql` +
  Library `.json` resource); valuesets in `ValueSet/` — dedupe against
  the shared layer: same canonical name/url + version → keep local +
  divergence note; different version → versioned filename.
- **Patient-ID collision policy (AM4a):** typed REJECTION by default
  (table of colliding ids + remediation — silent renaming would break
  expected MeasureReports). Opt-in `tc-` namespacing renames folder +
  resource ids AND rewrites List entries + expected-MR subject
  references in the same pass.

## 6. Q3 — "executes against only the 20 patients?"

It does not — verified live: evaluation returns ALL 22 rows with
boolean columns. "20" = the InAgeRange true-count display (w19/w20 are
46); IP = 18 after gender + encounters. Fix: result tables show ALL
evaluated patients + summary line "Evaluated 22 · Initial Population 18
· Numerator 10"; cell tables get an all-rows default with a filter
toggle. Display-only.

## 7. Q5 — evidence for derived defines (AM4d)

Confirmed expected today: `AgeInYearsAt` derives from
`Patient.birthDate` — a context-patient property, no contributing
resource. Design (generalized): audit leaves for ALL context-patient
property derivations — `birthDate`, `gender`, `deceased[x]`,
extensions — rendered as `target: Patient, attribute: <prop>, value:
<v>` evidence rows, landed in the evidence renderer + `explain_patient`
seam. Numerator-style resource evidence unaffected.

## 8. Q6 — editor/results placement

Text mode → whole-library Run appends to the bottom console (kept).
Cell mode → inline per-cell ONLY; no console duplication for cell runs.
Run history keeps both tagged `payload.surface: "console" | "cell"`
(existing entries default `"console"`); INV-4 unchanged.

---

## 9. Migration mapping (old → new)

| Legacy | New |
|---|---|
| `cql/<n>.cql` | `Library/<n>.cql` |
| (MADiE Library `.json` imports) | `Library/<n>.json` (stem-paired) |
| `valuesets/<f>.json` | `ValueSet/<id>.json` |
| `parameters/workspace.json` | `Parameters/workspace.json` |
| `measures/<name>.json` (flat) | `Measure/<m>/Measure/<name>.json` |
| `measures/<m>/data/<pid>/…` | `Patient/<pid>/…` + `Measure/<m>/List/TestCases.json` |
| `measures/<m>/expected/…` | `Measure/<m>/MeasureReport/<patientId>.json` |
| `views/<f>.json` | `Measure/<m>/ViewDefinition/<name>.json` (root `ViewDefinition/` when unattached) |
| `data/patients.ndjson` (monolith) | `Patient/<id>/…` folders; original → `_attic/` |
| `data/<pid>/*.json` bundles | split into `Patient/<pid>/<Type>/<id>.json` |
| `data/general/*` | root type folders (`Organization/`, `ValueSet/`, …) |

All migrations one-time on first boot, archive originals to `_attic/`.

---

## 10. Implementation slices (after approval; each Playwright-first)

1. **S22a — Workspace switcher + real demo dir (AM1).**
2. **S22b — Result display completeness (Q3).**
3. **S22c — Patient roster + editable patient folders (AM3).**
4. **S22d-1 — FHIR-type workspace layout + discovery + one-time
   migration (AM5–AM8, §1/§3/§9).**
5. **S22d-2 — Closure export/import over the List + collision policy
   (§5).**
6. **S22e — Normalize-on-ingest server path (§3).**
7. **S22f — Context-patient evidence leaves (§7).**
8. **S22g — Cell-run surface split (§8).**

Each slice: red Playwright test → fix → green → Muse → report.
