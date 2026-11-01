# 🎯 USER DIRECTIVES — CQL CLEANROOM WORKSPACE CONVERGENCE (S26)

<!--
This file is the PRIMARY MANDATE for the AI loop. It captures the full
S25/S26 escalation backlog agreed with Joel in-session on 2026-10-21
(see "Session decisions" below). The v0.0.17 post-S25 tree is the base.
-->

## Strategic Goal

Make the CQL Cleanroom's **connected mode the product surface**: real
FHIR workspaces on local files (the convention layout), the full
website UX fed from them, and a **single example/workspaces story**
across connected (workspace dirs) and standalone/WASM (MADiE-style
auto-zips). Plus a set of UX-surface corrections Joel raised live.

Everything runs through the existing devserver + web/cql-cleanroom
SPA. No engine/translator changes except the audit-evidence
enhancement (item 7).

## Session decisions (Joel, live 2026-10-21 — binding context)

1. Text CQL editor console: **Results tab ONLY** (output of every
   define statement); the Defines tab is REMOVED from the library
   context.
2. Measure surface (navbar > measure): **Measure Report + Funnel
   only**; its Defines tab is REMOVED.
3. Cells editor: takes up **ALL vertical space** (the rows where the
   docked console lives in text mode) — cells view is console-free
   and full-height.
4. BUG: switching to cms125-workspace still evaluated "3 patients"
   (demo dataset) — the auto-recalc heartbeat is browser-origin and
   never sees the server workspace kernel data. Connected-mode
   heartbeat must evaluate against the SERVER workspace dataset.
5. BUG: Valuesets pane shows nothing in connected mode (cms125's
   ValueSet/ folder is never surfaced). Wire it to the server
   workspace valuesets.
6. BUG: text-editor evidence click targets the wrong population
   (click InAgeRange -> initial_population evidence; also wrong
   patient p1). Fix click-targeting on the browser-origin path
   (rides the item-4 fix).
7. Audit enhancement: property-derived defines (AgeInYearsAt etc.)
   show "no contributing resources" — emit patient-property leaves
   (e.g. birthDate + age bounds) so evidence explains WHY. Builds on
   the context-patient audit leaves in the translator. Dual-engine.
8. Resource Builder: replace the Raw JSON checkbox with the SAME
   switch widget as the Cells/Text toggle (Form ⇄ / Raw ⇄;
   keep the parse-guard when leaving raw).
9. Workspace switcher moves from the header into **File > Workspace**
   submenu (connected only; active one checked; click = switch +
   reload). Retire the header control.
10. EXAMPLES = WORKSPACES: File > Open > Examples lists the bundled
    workspaces (connected: switches workspace). Build real-content
    workspaces for CMS69 and CMS125 from the repo's licensed fixtures
    (`tests/data/ecqm-content-qicore-2025`,
    `tests/data/dqm-content-qicore-2026`); REPLACE the synthetic
    cms125-workspace (a). Each full example workspace carries:
    - all libraries (includes), valuesets, test patients, measure
    - **expected results** authored from the fixture's OFFICIAL
      expected values (c)
    - a **ViewDefinition over the MeasureReports** to showcase the
      View tab
    - demo-workspace stays simple but gains ONE define that uses a
      valueset (local file)
11. STANDALONE (b): one workspace at a time, loaded from a
    **MADiE-zip-style browser-bundled asset bundle**. The bespoke
    `examples/<name>/` fetch-bundle path RETIRES; the MADiE loader
    becomes the single "open a package" path. Example zips are built
    from the workspaces by the same generator (zip == workspace
    content, one source).
12. Standalone boot control via **query parameter** `?example=cms125`
    (website embed sets it via the existing host handoff; the website
    flips its featured example to CMS125). No param -> clean boot
    (CleanroomDemo scratch stays available but NOT auto-run as the
    e2e-suite default; keep share/saved-workspace precedence).

## Framing

Groundwork-to-feature cycle — **no version bump** unless Joel asks.
Joel commits; no commits at any pipeline step.

## Work-type classification (agreed with Joel 2026-10-21)

| Items | Work type | Rationale |
|---|---|---|
| 4, 5, 6 | **bug_fix** | root-cause fixes with failing Playwright repros; 6 rides 4 (the browser-origin phantom-patient path disappears) |
| 1, 2, 3, 8, 9, 12 | **feature_implementation** (no design) | every design decision already made in-session |
| 10, 11 | **feature_implementation + inline design artifact** | architecture decided; the fixture→workspace mapping, expected-results pinning rules, and zip layout get a half-page WRITTEN contract (code-review auditable, NOT a gated FDD) |
| 7 | **feature_design → feature_implementation** | the only item with open design freedom: leaf shape/schema, qualifying expressions, narrative rendering, dual-engine parity, likely native rebuild. Precedent: context-patient audit leaves ran design-first (gate-approved note f317e9f1) |

## Pipeline

1. `bug_fix` — items 4, 5, 6 (connected-mode truth; de-risks everything downstream — the example workspaces cannot be demoed truthfully while the heartbeat evaluates the wrong dataset)
2. `feature_implementation` — items 1, 2, 3, 8, 9, 10, 11, 12 in the slice order below (items 10/11 write their inline design artifacts as their first unit)
3. `feature_design` — item 7 (audit property-leaves FDD; gated per ROLE_FEATURE_DESIGNER)
4. `feature_implementation` — item 7 (executes the approved FDD)
5. `code_review` — full campaign diff (all 12 items)

## Implementation slices (within pipeline step 2; ordered; each
journey-tested per the Playwright-First doctrine before it may be
called complete)

### Slice 1 — Workspace foundation + connected surfaces
- INLINE DESIGN ARTIFACT first (items 10/11 contracts): fixture→
  workspace mapping, expected-results pinning rules (fixture-official
  values), zip layout = workspace layout, MADiE-loader compatibility.
- Generator script (repo tooling) building from fixtures:
  `examples/demo-workspace` (valueset define added),
  `examples/cms69-workspace`, `examples/cms125-workspace` (real,
  REPLACES synthetic) — canonical layout (Library/, ValueSet/,
  Measure/, Patient/<id>/), reproducible.
- Item 9: File > Workspace submenu; retire header picker control.
- Item 10 (connected half): File > Open > Examples lists workspaces
  as switches (connected mode).
- Items 1+2: remove Defines tabs (library AND measure contexts);
  Results tab = every define (all-defines columns doctrine, S23-1).
  Update the two stale console.spec pins to this doctrine.
- Item 3: cells view full-height (claims the console rows).
- Item 8: builder Form ⇄ / Raw ⇄ switch widget.

### Slice 2 — Zip convergence (standalone)
- Autozip build from the workspaces (cms125.zip, cms69.zip, demo
  zip) — MADiE-compatible layout per the slice-1 design artifact.
- MADiE loader becomes the ONE package path; retire the
  examples/<name>/ fetch bundle (App.loadExample and
  static-cleanroom/examples/*).
- Item 12: `?example=` boot param + website host-handoff flips to
  cms125; no-param = clean boot; share/saved precedence kept.
- Update the website embed assets (web/website static snapshot) —
  coordinate with docs doctrine; do not break the WASM checklist.

### Slice 3 — Showcase
- Item 10 (showcase half): expected results from fixture-official
  values + MeasureReport ViewDefinition in both full workspaces;
  e2e proving Results -> Evidence -> Expected compare -> View.

## Acceptance gates (all binding)

1. **Playwright-First**: every UI/UX item is confirmed via
   Playwright BEFORE the fix lands (failing repro first, same test
   green after). Every handoff states 'repro'd via Playwright:
   <test name>'.
2. **Journey-Test Doctrine**: plan sections are written in
   USER-JOURNEY language; each plan promise has a JOURNEY-level
   Playwright test derived from the PLAN'S OWN WORDS. Campaign
   close-out includes the acceptance matrix (promise -> test) and a
   Joel checkpoint review before 'complete'.
3. **Existing suites stay green** (or explicitly updated with
   doctrine citations): s24-journey, s22c-roster, cell-mode, nav,
   console.spec, devserver pytest, vitest. The 2 pre-existing
   console.spec failures get RESOLVED by the item-1 doctrine change
   (update pins to all-defines columns), not left failing.
4. **DQM/conformance gate**: `python3 conformance/scripts/run_all.py`
   2832/2832 must hold at campaign end (item 7 may touch translator
   evidence paths — rerun the full gate after it).
5. **devserver pytest** green; new routes get new tests (workspace
   examples listing, valuesets listing).
6. **No engine seams in the devserver**; evaluation behavior comes
   from the operations layer as-is (AGENTS.md rule).
7. **Zero new required npm/pip dependencies.**
8. Zip format compatibility: the autozip must load through the
   EXISTING MADiE loader without loader changes being REQUIRED
   (loader changes allowed only as additive niceties, not format
   breaks).
9. **No commits** — Joel reviews and commits. Stage nothing.

## Focus Areas (cross-cutting)

- Single-writer discipline; this campaign shares the tree with no
  one — but DO NOT touch the uncommitted S25 working set beyond what
  the slices need (it is pre-review state for Joel).
- PROC_VALIDATION.md context rules (PYTHONPATH=/mnt/d/fhir4ds,
  fresh runs, filtered output).
- Rebuild + redeploy static-cleanroom/ after every UI change; e2e
  runs against the deployed bundle (vite preview for standalone
  specs, spawned devserver for connected specs).
- The two extension binaries must remain md5-stable unless item 7
  requires a native rebuild; if rebuilt, repo bundle == site-packages
  == md5 parity, conformance gate rerun.
- Fix root causes, no heuristic shims (e.g. item 4 is a data-flow
  fix, not a display patch).
