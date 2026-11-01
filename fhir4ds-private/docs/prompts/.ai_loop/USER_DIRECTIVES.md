# 🎯 USER DIRECTIVES — WASM function-surface parity campaign (2026-10-24)

> Swapped over the completed S26 directives (archived at
> `archive/20261024-wasm-surface/`). `state/evolution.json` was reset
> alongside this swap.

## Strategic Goal

Close the remaining **desktop ↔ browser (DuckDB-WASM) function-surface gaps**
for everything the CQL translator can emit, with **behavioral parity** — not
just name presence — and make the gap class detectable by the test suite.

Context (S32 discovery): v0.0.14 closed the *Catalog-Error class* (10
translator-reachable Python-only UDFs) but explicitly did **not** audit
functions that already had a `cql-macros.ts` fallback. `ToDate` was one: the
browser macro was `CAST(x AS DATE)` (returns DATE) while desktop Python returns
validated VARCHAR, which broke CMS125 population SQL with
`Cannot mix values of type DATE and VARCHAR in CASE expression`. `ToDate` was
fixed in S32 (C++ extension scalar, TS macro removed, wasm + wheel rebuilt,
standalone cells verified, conformance 2832/2832).

A three-connection audit (C++ extensions only = wasm surface; desktop
`register()`; `cql-macros.ts` names) then showed the remaining exposure:

- **48 public desktop-only names absent from the browser**, including the whole
  `ConvertsTo*` family, `CanConvertQuantity`, `ToLong`, `ToRatio`,
  `ExpandValueSet`, and the list-equality macros already covered by
  `BROWSER_MACRO_GAP_ALLOWLIST`.
- **~76 names present in both but with different implementations** (TS macro
  vs Python UDF/macro) — names match, bodies may not.
- `fhir4ds/operations/tests/test_macro_sync.py` enforces **name** parity only.

## Scope

1. Build a **behavioral surface harness** that executes the browser-equivalent
   surface (C++ extensions + the `cql-macros.ts` SQL extracted verbatim) and
   diffs it against desktop `register()` over a spec-grounded corpus
   (Appendix B examples + edge cases) for every translator-emittable function.
2. Port the **missing public conversion/terminology functions** to the C++
   extension so both runtimes share one implementation, and remove the
   corresponding TS macros:
   - `ToDateTime`, `ToTime`, `ToLong`, `ToRatio`
   - `ConvertsToBoolean/Date/DateTime/Decimal/Integer/Long/Quantity/Ratio/String/Time`
   - `CanConvertQuantity`
   - `ToString`/`ToInteger`/`ToDecimal`/`ToBoolean` only where the TS macro body
     diverges from the Python authority (verify first; many may already match).
   - Document `ExpandValueSet` as an accepted browser gap (requires the
     terminology `valuesets` table) unless a no-Python implementation is
     feasible without new data tiers.
3. Upgrade `test_macro_sync.py` from a name contract to a **behavior contract**:
   every non-allowlisted macro that exists on both surfaces must produce the
   same result and type on the harness corpus; intentional gaps stay
   allowlisted with a one-line justification and a stale-entry prune.
4. Keep the pre-existing allowlisted list-equality family out of scope unless
   the harness shows a real example workspace/measure hitting it in the
   browser.
5. Release integration: rebuild native + WASM extensions, rebuild the wheel,
   redeploy the Cleanroom static targets, and run all gates.

## Non-goals

- Re-porting functions already covered by v0.0.14 (cqlDivide, CQLMessage,
  coding_matches*, fhirpath_in_valueset, cqlChildren/Descendants,
  cqlDateTimeAdd, ratioCompare, ConceptToListCode).
- Implementing terminology data tiers in the browser.
- Changing translator semantics; this is a runtime-surface completion.

## Pipeline

1. `feature_design` — FDD (harness + port order + contract test design)
2. **WAIT_FOR_USER_APPROVAL** — Joel reviews the plan
3. `feature_implementation` — harness, C++ ports, TS macro removals, tests
4. `code_review` — campaign diff
5. `evolution` — targeted QA over the new surfaces (browser-path parity)
6. `pre_release` — version/wheel/artifact gates
7. `docs_audit` — release notes + website/WASM deployment
8. `scribe`

## Binding gates (every implementation iteration)

- Master conformance `python3 conformance/scripts/run_all.py` = **2832/2832**
  (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
- `fhir4ds/cql` pytest tree green (or only pre-existing documented failures).
- `fhir4ds/operations`, `fhir4ds/devserver`, `fhir4ds/fhirpath`, `fhir4ds/viewdef`,
  `fhir4ds/dqm` pytest trees green.
- `web/cql-cleanroom` vitest + the standalone/WASM e2e smoke (cms125 cells run
  without Catalog/Binder errors).
- C++ extension binaries rebuilt for **both** native and WASM, md5-verified
  across build/bundle/site-packages/public, and the wheel rebuilt before any
  deploy.
- No commits by the agent; Joel commits.

## Environment notes

- Repo `/mnt/d/fhir4ds`, branch `feat/cleanroom-redo-20261014` (HEAD
  `fb3e65fe` + uncommitted campaign work). WSL2: use long timeouts.
- Standalone: `cql-cleanroom-wasm.service` → http://127.0.0.1:5178/ (serves
  `web/website/static/cql-cleanroom`, default example `cms125-workspace`).
- Connected: `s26-review.service` → http://127.0.0.1:19250/cleanroom/.
- Deploy: `scripts/deploy_cleanroom_app.sh` (full-dist mirror + verification).
- Probe/audit artifacts: `/tmp/opencode/surface_diff.json`,
  `/tmp/opencode/macro_body_diff.json`.
