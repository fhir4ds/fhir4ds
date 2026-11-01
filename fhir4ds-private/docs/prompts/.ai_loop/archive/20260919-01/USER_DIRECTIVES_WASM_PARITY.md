# 🎯 USER DIRECTIVES — v0.0.14: WASM C++ Parity + Release Campaign

> ACTIVE DIRECTIVE — swapped over USER_DIRECTIVES.md on 2026-09-07 per
> Joel's instruction. `state/evolution.json` was reset alongside this
> swap (phase=INITIALIZER, workflow=null, pipeline_step=0).

## Strategic Goal

Ship **fhir4ds-v2 0.0.14** as the "browser-complete" release:

1. **WASM C++ parity feature** — implement 100% C++ (WASM) coverage of
   every UDF the CQL translator can emit, eliminating the browser
   runtime's dependence on Python-only UDFs. After this feature, the
   browser runtime (DuckDB-WASM + the two `.duckdb_extension.wasm`
   binaries) executes any translatable CQL library end-to-end with
   **no `cql-macros.ts` fallback for these functions** and no Catalog
   Errors.
2. **Complete the spec-compliance loop** with explicit Python↔C++
   extension parity verification for the newly ported functions.
3. **Infrastructure QA campaign over domains 6-10**, then full release
   prep: code review, pre_release, docs_audit (including release
   notes), scribe.
4. **medterm4ds 0.0.4 dependency bump** — next release candidate, with
   the deliberate MT-001 re-verification.

Non-regression on the master conformance gate (2832/2832 at campaign
start) is a hard constraint throughout.

## Standing Doctrine: AUTO-ADVANCE (NO USER APPROVAL GATES)

Per Joel's standing instruction (2026-09-07), this campaign runs
**without blocking on user approval**:

- **The `feature_design` WAIT_FOR_USER_APPROVAL gate is WAIVED.**
  Instead of stopping for human approval, the Feature Designer takes
  the refined plan through an independent **`/second-opinion` review**
  (default model from `~/.config/fleet/models.env`; on failure, pick
  another from the menu rather than stopping). Present the second
  opinion's view alongside the plan's own rationale. If the reviewer
  raises CRITICAL or unaddressed-HIGH concerns, iterate the plan and
  re-review once; if concerns remain after one re-review, adopt the
  safer option, record the disagreement in the FDD, and CONTINUE —
  do not stop.
- **Never adopt a second opinion silently** (standing rule): record
  its verdict and what was changed/ignored in the FDD's self-audit
  section.
- **Auto-advance through the entire pipeline** (feature → implement →
  review → spec compliance → QA → review → pre-release → docs →
  scribe). The only permitted stops are the standing blocking
  conditions: destructive/irreversible actions, secrets, or a
  genuinely unresolvable ambiguity that changes clinical/business
  semantics — surface those and pause; everything else advances
  autonomously.
- This waiver applies ONLY to this campaign's approval gates; all
  other standing loop rules (Recovery Gate, gate non-regression,
  clobber guards, binary freshness checks) remain fully in force.

## Target Version

**0.0.14** (current `pyproject.toml` is 0.0.13; Release Engineer bumps).
All 7 `__version__` sites move in lockstep per the standing doctrine.

## Pipeline

1. `feature_design` (FDD → architecture self-audit → refined plan →
   `/second-opinion` review in lieu of human approval → auto-advance;
   see AUTO-ADVANCE doctrine above)
2. `feature_implementation` (execute the approved plan; includes
   testing the rebuilt WASM extensions against cql-clinic in the
   browser)
3. `code_review` (audit the feature diff)
4. `spec_compliance` (resume/complete the parked spec-compliance loop
   via ROLE_SPEC_COMP_ORCHESTRATOR.md + spec_schedule.json, with
   dual-engine parity as a first-class check)
5. `evolution` (QA campaign, domains 6-10, 15 iterations)
6. `code_review` (full 0.0.14 diff audit)
7. `pre_release` (version bump, medterm4ds 0.0.4 pin, wheel build,
   clean-venv install gates)
8. `docs_audit` (release notes, website, WASM wheels refresh + deploy)
9. `scribe`

---

## Feature: WASM C++ Parity (steps 1-2)

### Background (verified inventory, 2026-09-07)

The browser executes SQL on DuckDB-WASM, which cannot host the Python
UDF tier (`con.create_function`). Desktop parity (Python fallback vs
C++ extension, master conformance gate) is NOT browser parity. A fresh
three-way inventory (Python `create_function` registrations ×
C++ `ScalarFunction`/`RegisterSpecialScalar` registrations in both
extensions × `web/wasm-demo/src/lib/cql-macros.ts`) found **13 Python
UDFs with no C++ counterpart and no TS macro**:

**Reachable from translated CQL (10 — MUST implement in C++):**

| Function | Translator refs | Surface |
|---|---|---|
| `cqlDivide` | 6 sites | CQL `/` division (exact Decimal, scale 8) |
| `cqlChildren` | 6 sites | `Children()` |
| `cqlDescendants` | 6 sites | `Descendants()` |
| `cqlDateTimeAdd` | 3 sites | DateTime ± Quantity arithmetic |
| `coding_matches` | 9 sites | dynamic code `~` equivalence |
| `coding_matches_exact` | 3 sites | dynamic code `=` equality |
| `CQLMessage` | 6 sites | `Message()` operator (Error severity raise) |
| `ratioCompare` | 6 sites | Ratio equality/equivalence |
| `ConceptToListCode` | 3 sites | `convert Concept to List<Code>` |
| `fhirpath_in_valueset` | 3 sites | `in` ValueSet over FHIR paths (fhirpath ext) |

**Dead registrations (3 — DELETE the Python registration instead of
porting; zero translator references):** `ConvertQuantity`,
`cqlNormalizeTZ`, `cqlDateTimeSubtract`.

**Name reconciliation (cosmetic but in scope):** Python registers
`MillisecondsBetween`/`WeeksBetween` while C++ registers
`millisecondsBetween`/`weeksBetween`; the translator emits neither
PascalCase form. Align names (prefer the C++ casing; delete the
unreferenced Python registrations or rename both).

### Semantics authority

The Python implementations remain the **conformance authority** on
desktop (the `_PYTHON_PREFERRED_CPP_CONFLICTS` doctrine is unchanged).
Each new C++ function must be **behaviorally identical** to its Python
counterpart on the full documented edge surface, not merely on the
happy path:

- `cqlDivide`: exact base-10 Decimal division at implementation scale 8
  (ROUND_HALF_UP), NULL on null operands / zero divisor / non-numeric
  / result outside the 28-digit extent. DuckDB `/` promotes to DOUBLE —
  the C++ implementation must use exact integer/long-division on the
  operand text (prior art in-repo: `exactDecimalRatioText` and
  `powerDecimalExactText` in
  `extensions/fhirpath/src/fhirpath/evaluator.cpp`).
- `CQLMessage`: typed SQL macro around `error()` with COALESCEd code /
  message text (Python `udf/math.py` + `macros/math.py:184` are the
  reference).
- `coding_matches(_exact)`: `udf/clinical.py` reference; absent literal
  elements must be absent in the coding for `_exact`.
- All others: mirror the Python UDF in `fhir4ds/cql/duckdb/udf/`
  element-for-element, including NULL/edge behavior.

### Hard constraints (feature)

- **No behavior change on desktop.** Python-preferred shadowing stays;
  the master conformance gate must hold unchanged.
- **Dual-engine parity tests** for every ported function:
  forced-Python fallback vs native-loaded C++ vs no-Python C++-only
  connections, on the Python UDF's documented edge cases (adapt the
  existing parity-test patterns in
  `fhir4ds/cql/duckdb/tests/integration/`). Include the three
  cql-clinic lesson solutions as end-to-end fixtures — `data-types`
  exercises `cqlDivide` and must pass on the no-Python surface.
- **Dual-target rebuild + redeploy:** native builds deployed to
  `fhir4ds/*/duckdb/extensions/` + site-packages; WASM builds via
  `make wasm_eh` from BOTH `extensions/fhirpath` and `extensions/cql`
  with the pinned emsdk 3.1.56 (required for
  `@duckdb/duckdb-wasm@1.33.1-dev41.0`); `.wasm` binaries copied to
  BOTH `web/wasm-demo/public/extensions/` AND
  `web/cql-clinic/public/extensions/`; verify md5 parity
  (build == repo bundles == deployed copies).
- **No TS-macro fallbacks for these functions:** after implementation,
  remove any cql-macros.ts entries that exist solely to cover them
  (none of the 13 have one today — keep it that way) and do not add
  new ones. The browser surface is C++-only for these functions.
- **`__EMSCRIPTEN__` drift guard:** no new divergent WASM-only
  branches; ported functions identical across native and WASM builds.

### Feature validation (including cql-clinic browser test)

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/ -x -q` (new parity files included)
- `python3 conformance/scripts/run_all.py` → gate holds
- `cd web/wasm-demo && npx playwright test` → playground /
  web-component / cms-measures all green (never skip cms); add a
  playground case exercising `10.0 / 3.0` division end-to-end
- **cql-clinic browser test**: `cd web/cql-clinic && npm run build`,
  then dev/preview smoke — all 3 lessons translate → loadFixtures →
  execute → grade green with the rebuilt extensions (the original
  `cqlDivide` Catalog Error repro must pass)

---

## Spec Compliance (step 4)

Resume the parked spec-compliance loop (state/evolution.json sat at
phase ARCHITECT, pipeline `["evolution"]`, CQL-19 chunk notes before
this campaign's reset — the CQL-19 work itself was verified CLEAN with
gate 2832/2832 and DQM 47/47 per its archived handoffs; treat the
parked loop as superseded by this campaign and run the orchestrator
over the remaining schedule). Requirements for this cycle:

- **Dual-engine parity is a first-class check for every remaining
  chunk**: native/C++ extension path vs Python fallback path compared
  on every probed case (per the standing chunk-test doctrine).
- The 10 newly ported C++ functions get **spec-grounded parity
  probes** (CQL 1.5 Appendix B semantics × Python authority × C++ ×
  no-Python surfaces), not just the generic chunk sweep.
- Master gate non-regression after every chunk.

## Evolution Campaign (step 5)

Domains **6-10** per SPEC_QA_DOMAINS.md, each receiving SKEPTIC →
HISTORIAN → EXPLORER (15 iterations minimum). Requested configuration:

- `min_iterations`: 15
- `max_iterations`: 24
- `exhaustive_mode`: false
- `target_version`: `0.0.14`
- `qa_schedule`: domains in order **6, 7, 8, 9, 10** (iterations 1-3 =
  domain 6, 4-6 = domain 7, ... 13-15 = domain 10)

**Domain 6 — Data Ingestion and Schema** (FHIRDataLoader, resources
table): Patient-typed patient_ref attribution (loader +
FileSystemSource), versioned-ref resolve, BOM/case-insensitive
directory handling, per-entry bundle validation, Arrow bulk path under
pathological shapes. Hunt regressions and NEW gaps.

**Domain 7 — Performance and Scale**: 1k/10k/50k synthetic patients,
memory-leak detection (tracemalloc), concurrent connections. Hunt
Scaling Cliffs and memory spikes — do NOT flag linear slowdown as a
bug. Include the new C++ functions in the query mix (e.g.
division-heavy, Children/Descendants workloads) to confirm no WASM/
native perf cliff was introduced.

**Domain 8 — Error Handling, Robustness, API Contract**: actionable
errors vs internal SQL leaks, typed exceptions, closed connections,
invalid JSON. Re-verify the output_columns/parameters validation
guards and the adjudicated bare-connection doctrine
(`test_evaluate_measure_missing_udf_catalog_error_is_not_rewritten`).

**Domain 9 — Audit Evidence and DQM**: evidence tied to resource IDs,
exclusion/exception population causality, one-row-per-patient audit
output, numpy-safe population masks. Confirm the C++ ports did not
alter DQM SQL shape or attribution.

**Domain 10 — Installation and Environment**: clean install/import,
C++ extension load vs Python fallback (no silent fallback — unsigned
dev-build WARNING still surfaces), `__version__` consistency across
all 7 sites, `pip check`, `register(con)` idempotency. **Dual-Python
validation** (3.10 AND 3.11 — 3.11 venv at /tmp/py311env or recreate
with `uv venv --python 3.11`). Verify the WASM extension binaries ship
in the wheel and md5-match the repo bundles.

## Code Review (steps 3 and 6)

- **Step 3 review**: the feature diff only — C++ ports, deleted dead
  registrations, name reconciliation, parity tests, binary freshness
  (md5 build == bundles == site-packages for BOTH extensions, native
  AND wasm), clobber spot-checks on existing fix symbols.
- **Step 6 review**: the full 0.0.14 diff (feature + spec-compliance
  fixes + evolution fixes + medterm4ds bump). Carry the open REV
  ledger forward (REV-002/003/005/009..016 etc.) — re-verify status,
  don't re-litigate settled doctrine. The 7 known pre-existing
  fhirpath parity failures outside the conformance gate remain
  documented, not silently "fixed".

## Pre-Release (step 7)

- Version bump 0.0.13 → 0.0.14 across pyproject + root + all 6
  subpackage `__version__` constants; `fhir4ds/tests/test_version.py`
  green.
- **medterm4ds 0.0.4**: bump the bounded pin on BOTH extras
  (`terminology`, `ner`) from `>=0.0.3,<0.0.4` to `>=0.0.4,<0.0.5`;
  `pip install medterm4ds==0.0.4`; diff-audit the 0.0.3→0.0.4 surface
  before trusting adapter behavior. MT-001 deliberate re-verification:
  in_process_adapter integration tests, DQM terminology suite,
  conformance gate, FHIR4DS_TERMINOLOGY_* env modes. 0.0.4 carries the
  new artifact-manifest layer (embedding_space_id) — verify INV-1
  (manifest validation never at import), semantic-family gates fire
  only when the semantic path loads (DQM lexical/canonical jobs
  unblockable), and the search_index_dir single-dir contract. Verify
  the wheel METADATA carries the new bound on both extras.
- Wheel build with BOTH bundled extensions (native + wasm binaries
  fresh); clean-venv install smoke (`pip check`, version, register
  flags, native function battery); dual-Python CI invocation green.

## Docs Audit (step 8)

- **Release notes**: `releases.md` v0.0.14 section — WASM parity
  feature (browser now executes full translatable CQL surface with no
  macro fallbacks for the ported functions), spec-compliance + campaign
  fixes, medterm4ds 0.0.4 bump, conformance baseline.
- Website: PRODUCT_VERSION + version assertions updated; any
  wasm-engine docs mentioning browser function limitations refreshed.
- **WASM wheel refresh + deploy**: build the 0.0.14 wheel, copy to
  `web/wasm-demo/public/` (exactly ONE wheel), rebuild wasm-demo,
  deploy snapshot `rm -rf web/website/static/wasm-app && cp -r
  web/wasm-demo/dist/. web/website/static/wasm-app/` (the most-missed
  step); **also refresh `web/cql-clinic/public/` wheel + extensions**
  so cql-clinic ships the release binaries; micropip deps=False rule
  verified intact; Playwright e2e green on the final build.

## Scribe (step 9)

Standard draft-commit preparation per ROLE_SCRIBE.md. Joel commits.

## Out of Scope

- The `_PYTHON_PREFERRED_CPP_CONFLICTS` interval family (already has
  C++ WASM implementations; browser works today).
- cql-macros.ts cleanup beyond the 13 functions' coverage.
- Translator changes (the translator already emits these names).
- Publishing cql-clinic to the website/GitHub Pages (separate effort;
  docs_audit only refreshes its bundled wheel/extensions).
