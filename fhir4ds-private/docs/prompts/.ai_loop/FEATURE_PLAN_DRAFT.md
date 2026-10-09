# FEATURE: c-cleanroom-ux5 — User Feedback Round (8 items)

**Status:** DESIGN DRAFT for conductor review — 2026-10-08
**Worktree:** /mnt/d/fhir4ds-ux5-20261008 (branch feat/cleanroom-ux5-20261008 @ 3ccb97bf)
**Process:** design doc first → conductor review → slices → Muse gate

---

## 0. MADiE research findings (grounds items 3 + 4)

Sources read (cloned @ /tmp/opencode/madie_research): `MeasureAuthoringTool/measure-service`,
`madie-fhir-service`, `packaging-utility` (qicore411 + qicore6 impls).

### 0.1 Simple-export package ZIP (PackagingUtilityImpl.qicore411, inherited by qicore6)

```
<Title>-v<version>-FHIR.json      # the full Measure+Library(+valuesets) Bundle, pretty JSON
<Title>-v<version>-FHIR.xml       # same, XML
<Title>-v<version>-FHIR.html      # human-readable w/ CSS
cql/<LibName>-<version>.cql        # one per CQL library (includes FHIRHelpers etc.)
resources/measure-<name>-<ver>.json/.xml
resources/library-<name>-<ver>.json/.xml
```
The measure Bundle carries valuesets inline (`compose` from their terminology service).

### 0.2 Test-case export ZIP (madie-fhir-service TestCaseBundleService)

```
<patientId>/<EcqmTitle>-v<ver>-<Series?>-<Title>.json   # one FHIR Bundle PER TEST CASE
```
- Each test case = **one Bundle for one patient** (all that patient's resources).
- The LAST bundle entry is a synthesized **MeasureReport** with:
  - `meta.profile = cqfm-test-cases` profile,
  - `modifierExtension` `isTestCases = true`,
  - extension `cqfm-inputParameters` → `contained[0]` Parameters (period etc.),
  - `group[].population[]` = **EXPECTED counts** (id = population display id),
  - `group[].measureScore` + stratifier expectations, composite-score support.
- Export types can rewrite ids (`madie-generated-uuid`) — default keeps authored ids.

### 0.3 Compatibility classification (per user clarification: additive OK, test-data conflicts must be fixed)

**(a) THEIR shapes (must import cleanly):**
- Package ZIP: root `<Title>-v<ver>-FHIR.json/.xml/.html` measure bundle + `cql/<Lib>-<ver>.cql` + `resources/*.json|.xml` (§0.1).
- Test-case ZIP: `<patientId>/<EcqmTitle>-v<ver>[-Series]-<Title>.json` — one Bundle per test case; final entry = expected MeasureReport (§0.2).

**(b) OUR conventions that stay (additive, no conflict):**
- Per-patient NDJSON files in `data/` — MADiE never ships NDJSON, and our loader treats
  `.ndjson` vs `.json` by suffix (kernel.py); both coexist in the same dir tree.
- Our parameters-as-Parameters resource, provenance extensions, baseline naming — none
  read by MADiE tooling; additive by the user's rule.
- Our expected store keyed per patient (MADiE's own MR shape, separate dir) — additive.

**(c) Conflicts found → fixes (S3/S4 scope):**
1. **Trailing expected-MeasureReport ingestion** (the real incompatibility): our
   `load_bundle` (operations/dataset_ops.py) loads EVERY bundle entry, so a MADiE test
   bundle dropped into `data/` loads its expectation MeasureReport as a resource
   (pollutes `resources`, breaks patient counts).
   Fix (two layers): (i) importer strips the trailing `isTestCases`-marked MeasureReport
   entry into the expected store before writing the patient bundle; (ii) DEFENSIVE:
   `load_bundle` skips MeasureReport entries carrying the `cqfm-test-cases` profile /
   `isTestCases` modifier extension — protects users who drop raw MADiE bundles into
   `data/` without the importer, and cannot match any legitimate data resource.
2. **Folder-per-patient layout**: NO fix needed — discovery `rglob("*")` over data_dirs
   already picks up `data/<patientId>/*.json` recursively (verified in discovery.py).
3. **XML entries** in their package zips: NO fix — `.json` twins always exist; our
   suffix filters (.json/.ndjson) simply ignore the `.xml` files.

---

## 1. In-app VSAC config (item 1)

**Today:** `[terminology]` in fhir4ds.toml (provider/base_url/timeout/api_key_env); key
value only ever from env by NAME. No in-app editor.

**Design:**
- New `/api/terminology/config` GET/POST:
  - GET returns current settings + `key_env_resolves: bool` (does the env var exist in
    the server process? never the value) + provider health probe result.
  - POST body `{provider?, base_url?, timeout_seconds?, api_key_env?}` — VALIDATED
    (allowlisted keys, types), then **written back to fhir4ds.toml** preserving other
    content/comments as text where possible (regex-preserving rewrite; tomllib cannot
    round-trip comments — strategy: line-oriented edit of the `[terminology]` block,
    append block if missing; documented limitation).
  - Raw key values remain REJECTED at the API (server never accepts a key value, only
    a var name) — hard guard + test.
- UI: a Terminology settings dialog (gear next to terminology status pill):
  fields provider (vsac/http/off), base_url, timeout, api_key_env; "Test connection"
  (uses existing /api/terminology/preview with a tiny known OID, or is_healthy-style);
  Save writes toml + restarts terminology holders (endpoints are lazy holders — reset
  `_terminology_endpoint_holder`/`_umls_endpoint_holder` on write; kernel untouched).
- Slice: API+tests → dialog UI → e2e.

## 2. File/directory pickers (item 2)

**Today:** datasets/cql/valuesets/views discovered by convention dirs + `[dev]`
manifest in fhir4ds.toml (config.py `load_config` merge order convention > manifest >
flags) + FS watcher.

**Design:**
- Server-side directory listing API for pickers: `/api/fs/list?path=...` restricted to
  the workspace root + subdirs (path traversal guard, tests). Browser file `<input
  type="file" webkitdirectory>` NOT usable for server-side loading (browser sandbox);
  instead the picker browses the SERVER filesystem via /api/fs/list rooted at the
  workspace (with an explicit "go up" boundary at workspace root; absolute-path entry
  field for outside-root dirs).
- `POST /api/workspace/add-path` `{kind: cql|valueset|measure|data|view, path}`:
  validates the path exists (dir or file), appends to `[dev]` manifest in
  fhir4ds.toml (same line-oriented writer as item 1), triggers rescan + watcher
  update, returns the new snapshot. Duplicate-safe (dedup already in `merged()`).
- UI: "+ add" button on each rail section header opens the picker dialog (browse +
  path entry); search field filters the listing client-side.
- Slice: fs API + add-path API + toml writer shared with item 1 → rail buttons → e2e.

## 3. Test-cases rework → EXPECTED-RESULTS EDITOR (item 3) — structural

**Today:** TestsPane = per-define boolean grid (patient × define expect true/false)
posting /api/verify. MeasurePane already has expected-MR paste/compare + v4.2
"Save as expected baseline" (measures/expected/<name>.baseline.vN.json capture-from-run).

**Design — expected MeasureReport becomes the PRIMARY test surface:**
- New ExpectedResults pane replaces the bottom TestsPane grid:
  - **Capture from run** (primary flow): run the measure over the loaded dataset →
    per-patient actual MRs listed in an editable grid → user tweaks values to intent →
    saved as the expected baseline (extends v4.2 baseline store; per-patient files
    keyed by patient id, content = cqfm-test-cases-style MeasureReport, i.e. THE
    MADiE shape from §0.2).
  - **Compare view**: run tests = execute measure → diff actual vs expected
    (normalization via existing /api/measure/compare) → pass/fail per patient with
    drift details.
  - **Import from MADiE** (item 4 seam): expected MRs parsed out of MADiE bundles.
- **Boolean per-define assertions: RETIRED from the grid, folded in as a fallback
  lane**: when the open library has no measure (plain CQL), the pane degrades to the
  existing /api/verify define-check surface (same engine work, kept — the grid UI
  goes; a compact "define checks" section renders inside the same pane). Rationale:
  define checks remain useful for library-level TDD; MR expectations are the
  user-facing concept.
- Slice: capture-from-run per-patient baselines (API reuses measure/run +
  baseline/save extended with patient key) → pane UI → MADiE import (4) → retire grid.

## 4. MADiE import (item 4)

Per §0: two importers.
- **Package ZIP import** (`POST /api/madie/import-package`, multipart or path):
  - `<root>.json` measure bundle → parse Measure + Libraries + valuesets; CQL text
    extracted preferentially from `cql/*.cql` (authoritative, human-readable) into
    workspace `cql/<lib>.cql`; valuesets from bundle compose → `valuesets/*.json`
    (VSAC-adapter-style file per valueset); measure metadata → `measures/`.
  - resources/*.json redundant with the bundle — used only as fallback.
- **Test-case ZIP import** (`POST /api/madie/import-tests`):
  - `<patientId>/*.json` bundles → strip trailing expected-MeasureReport entry →
    patient bundle lands in `data/<patientId>/<case>.json` (new accepted layout,
    §0.3); expected MRs land in the item-3 expected store keyed by patient.
  - Verifies `isTestCases` marker before treating the last entry as expectations.
- Both write via the same add-path/manifest machinery (item 2) so the watcher picks
  them up; a kernel restart hint appears (existing stale banner pattern).
- Slice: research-verifier unit tests on synthetic MADiE-shaped zips (built from the
  §0 source reading) → package importer → tests importer → e2e happy path.

## 5. Builder value[x] layout (item 5)

**Today:** choice-arm child fields (Quantity value/unit, etc.) render inline in one
`dev-rbchoicerow` (cramped).

**Design:** when a choice arm (or any complex leaf like Quantity/Range/Period/Ratio/
Coding) is selected, its child fields render as their own labeled rows beneath the
choice selector (stacked `dev-rbfieldrow` per child: label left, input right) —
reuse the existing generic child-row renderer instead of the inline widget; the JSON
view stays authoritative. Pure CSS/markup change + minor state plumbing
(setQuantityObj already fieldwise). Slice: small, bundles with item 8 UI slice.

## 6. Slide-out nav (item 6)

**Design:** current left rail (datasets/valuesets/libraries sections) becomes a
level-1 icon rail (fixed ~48px: Datasets, Terminology, Libraries, Builder, Views,
Tests, Settings). Clicking opens a level-2 slide-out panel (~280px) with that
section's list + search + add/import actions; the center editor shifts right
(CSS grid transition). State: `railSection` + `railOpen` replace today's
`railView`-driven center switch for these sections; center keeps editor/builder.
Esc/click-outside closes. Keyboard: alt+1..7. No new server surface.

## 7. Patient-resources slide-out (item 7)

**Design:** second slide-out (opens from the right over results, ~360px) when a
patient is selected (patient chip in results grid / expected-results rows).
- New `GET /api/patient/resources?id=...` → kernel query `resources` joined on
  patient_ref (loader already maintains patient_ref; distinct from /api/patients
  which lists ids) grouped by resourceType; includes each resource's id/status/date
  + JSON peek (first 200 chars) with "open in builder" action (existing onEditInBuilder).
- Old-wasm pattern parity: list by type, click → detail view inside the slide-out.

## 8. Resizable panes + SQL surfacing + errors placement (item 8)

- **Resizable:** left rail/slide-out and right output pane get drag handles
  (pointer events, min/max clamps, persisted to localStorage; CSS grid template
  driven by state). No lib dependency.
- **SQL missing — investigation:** output area HAS an sql tab; `setSql` is wired
  only for translate/evaluate/cells-run. **measure/run, verify, view/run return
  SQL server-side (audit shows /api/measure/run + /api/view/run build SQL) but the
  UI discards it** — fix: propagate `sql` through those response types into the
  shared `sql` state and auto-switch offers a "Show SQL" toggle on every result
  header (button, not auto-tab-switch). VD pane: surface generated SQL under the
  run output (VD-SQL parity with old wasm).
- **Errors tab proposal (per user ask):** KEEP severity split internally; RETIRE
  the standalone errors tab — diagnostics render as a collapsible section at the
  top of the results view (red banner w/ count; expand for list), SQL tab stays.
  Rationale: errors-in-context beats a separate hop; severity still color-coded.

---

## Slice plan (implementation order after conductor approval)

1. **S1 config-writer + fs/add-path APIs** (items 1+2 server) — shared toml writer.
2. **S2 VSAC dialog + picker UIs** (items 1+2 client).
3. **S3 expected-results core** (item 3: per-patient baselines + pane; grid retired).
4. **S4 MADiE importers** (item 4; extends S3 expected store + S1 add-path).
5. **S5 nav + patient slide-outs** (items 6+7).
6. **S6 builder layout + resizable + SQL/errors** (items 5+8; pure-UI slice).
7. **Muse gate** over the full slice set; fixes; final report.

Each slice: tests (pytest + e2e where UI), tsc, vite build, gates, one commit.
