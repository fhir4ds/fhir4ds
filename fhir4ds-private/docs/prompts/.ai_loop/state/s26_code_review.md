# S26 Campaign Code Review (code_review step, iter 8)

Scope: full uncommitted campaign diff (77 files vs HEAD fb3e65fe + S25
working set). Review method: line-diff read of all non-asset source
files, injection probes, gate reruns, binary freshness checks.

## Verdict: CLEAN_WITH_NOTES

No CRITICAL/HIGH findings. Three LOW notes, all informational.

## Security review

- `_route_resource_replace` path construction: `root/Patient/<rid>/...`
  COULD traverse on a hostile `rid`, but `validate_resource` runs FIRST
  and enforces the FHIR id charset `[A-Za-z0-9-.]{1,64}` — probed
  `../../etc/passwd` → rejected at validation. VERDICT: safe (defense
  via the validate gate; `. joinpath` stays inside root).
- `/api/fs/list` sandbox + `/api/workspace/switch` name-matching
  against `_workspace_roots()` — no new unsandboxed path surfaces.
- Frontend: no dangerouslySetInnerHTML/eval/secret surfaces in the
  diff; parameter values flow through JSON bodies only.
- Zip loader (`importMadiePackage` extensions): valuesets/tests
  reading is pure `JSON.parse` over in-memory entries — no eval, no
  path writes.

## Item-7 correctness review

- The 3-tuple (`attr, value SQL, operator`) at both S22f sites; the
  cte_manager consumer indexes `[0]`/`[1]` positionally (back-compat).
- Mid-implementation bug (found + fixed in-loop): a de-indented
  `props.setdefault` escaped its `current_def` guard on the AgeAt site
  → UnboundLocalError on query-scope age calls. Caught by the existing
  `test_context_patient_leaf_review_guards`, fixed, suite green.
- Metadata-only invariant held: population SQL contains no audit
  macros; CMS125 population SQL md5-stable; conformance 2832/2832
  (ViewDef 144 / FHIRPath 935 / CQL 1706 / DQM 47) with the change.

## Notes (LOW, informational)

1. `TranslateResult.to_dict()` serializes `patient_property_defs` as
   `{col: [attr, op]}` (list form) while the dataclass holds tuples —
   consumers must not assume tuple shape from JSON. Documented here;
   envelope consumers today are internal.
2. `expectedItems` MADiE contained-Parameters subject extraction reads
   only the FIRST Parameters resource in `contained` — MADiE fixtures
   carry exactly one; a multi-Parameters MR would under-count. Fixture
   shape is stable.
3. `git status` shows `M node_modules/.vite/vitest/.../results.json`
   (a vitest cache artifact tracked by accident from an earlier era)
   and `M conformance/reports/dqm_report.json` (gate output refresh —
   content verified 47/47). Both are Joel-commit decisions, not
   campaign code.

## Gate reruns (final tree)

- operations pytest 25/25; devserver+operations 435/435
- cql unit 1712/1712
- conformance run_all.py: SUCCESS 2832/2832 (100%)
- vitest 195/195; website typecheck + build clean
- cleanroom e2e: s26a 3/3, s26b 4/4, s26c 2/2, s24 4/4, s22c 2/2,
  cell-mode 8/8 (three consecutive full runs after one S8 flake under
  load — passes isolated; WSL/drvfs timing, not logic), nav 9/9,
  console 12/12, examples 2/2
- Extension binaries: NO changes in the diff (Python/TS-only campaign
  as designed); repo bundle md5s cql ec7b9e16 / fhirpath 1b7a33e0.

## Acceptance matrix (plan promise → journey test)

| Promise (USER_DIRECTIVES) | Pinning test |
|---|---|
| (1) text editor Results-only, no Defines tab | s26b-3 (console-tab-defines count 0) + console.spec results-table repin |
| (2) measure surface MR+Funnel only | s26b-3 tabs list assertion (CONTEXT_TABS) |
| (3) cells full-height, no console | s26b-4 + S25-1 pin (s24-journey) |
| (4) connected heartbeat = server dataset | s26a-1 (w77/w78 rows + run origin server) |
| (5) Valuesets pane from workspace | s26a-2 (truth-vs listed) |
| (6) evidence click = clicked define | s26a-3 first click (IsFemale own leaf) |
| (7) property-derived defines explain WHY | s26a-3 second click (AgeYears birthDate derived leaf) + operations test_context_patient_property_leaf_non_boolean_defines |
| (8) builder Form⇄/Raw⇄ switch | builder-raw-toggle role=switch (s22c raw round-trip path) |
| (9) File>Workspace replaces header picker | s26b-1 (picker gone, menu lists workspaces, active checked) |
| (10) examples=workspaces, fixture-official expecteds, VD showcase | s26b-2 (three workspaces listed) + s26c-1 (6 fixture MRs) + s26c-2 (results/expected/View journey) |
| (11) standalone = MADiE zip only | fresh-default-cms69 (?example= zip boot) + example-autorecalc (zip loads, includes, MP prefill, 62-row run) + embed regressions (cms125 zip) |
| (12) ?example= + website cms125 | CleanroomWC default-example=cms125-workspace + embed-regressions visit-2 pin |

Honest-gap registry: cms125 Claim/EOB numerator cases (2/6) mismatch
their fixture pins under the official v0.4.000 CQL — the fixtures were
generated against the DQM draft logic requiring FHIRCommon/USCoreCommon
(absent from the repo). The compare surface shows this truthfully.
