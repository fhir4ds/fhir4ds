# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Prepare and ship **fhir4ds-v2 0.0.15**. Three bodies of work, in order:

1. **DuckDB version upgrade** — move the single-pin DuckDB floor from 1.5.2
   to the latest stable upstream release (full Dependency Upgrader workflow:
   submodules, native + WASM rebuilds, loader gates, pyproject pin,
   website/web redeployments, md5 parity, full conformance gate).
2. **External pressure-test remediation** — fix the confirmed bugs and
   guardrails from the independent 0.0.14 pressure-test report (installed
   wheel, Python 3.10, DuckDB 1.5.2, suites t01–t12 in /mnt/d/fhir4ds-test/):
   F1 hard bug, U1–U3 silent-failure guardrails, D1–D8 doc/behavior
   mismatches. **F2 was adjudicated NOT A BUG** (see below — official
   fixtures pin the opposite of the pressure-test's expectation).
3. **Full-tree evolution QA campaign** — domains 1–12, three personalities
   each (SKEPTIC, HISTORIAN, EXPLORER), 36 iterations, on the upgraded
   DuckDB — then code review, release prep, docs audit, scribe.

Non-regression on the 2832-test master gate (on the NEW DuckDB pin) is a
hard constraint throughout.

## Target Version

**0.0.15** (current pyproject is 0.0.14; the Release Engineer bumps).
medterm4ds bound stays `>=0.0.4,<0.0.5` — no bump this cycle.

## Pipeline

1. `dependency_upgrade` (duckdb_upgrade_mode: upgrade)
2. `bug_fix` (pressure-test findings below)
3. `evolution` (36 iterations)
4. `code_review`
5. `pre_release`
6. `docs_audit`
7. `scribe`

If the DuckDB upgrade hits a hard blocker (C++ API redesign required,
gate regression unfixable), execute the Upgrader's Recovery Gate (rollback
to md5 snapshot), record `BLOCKED_ENVIRONMENT`, and CONTINUE the pipeline on
the 1.5.2 pin — the pressure-test fixes and QA campaign must not stall on
the upgrade. Joel decides whether to re-attempt the bump post-campaign.

## DuckDB Upgrade (first — everything downstream tests on it)

Execute `ROLE_DEPENDENCY_UPGRADER.md` with:
- `target_duckdb_version`: latest STABLE upstream release as determined by
  Phase 1 recon (record the exact version chosen; do NOT target
  dev/nightly builds).
- `duckdb_upgrade_mode`: `upgrade`.
- `target_version`: `0.0.15`.

Non-negotiables (from the role's invariants):
- The matched triple moves together: vendored submodules (both extensions),
  `pyproject.toml` exact pin, both `extension.py` loader gates.
- Native rebuild with FRESH build trees (stale CMake caches → "System is
  unknown to cmake"); deploy to repo bundle + site-packages; clear
  `~/.duckdb/extensions` caches.
- WASM rebuild (`make wasm_eh`, emsdk 3.1.56) for BOTH extensions; deploy
  to `web/wasm-demo/public/extensions/`, `web/cql-clinic/public/extensions/`,
  AND `web/website/static/wasm-app/extensions/`; md5 parity
  build == all deployments.
- Graceful-degradation probe FIRST (Phase 3): current wheel + candidate
  duckdb in a throwaway venv must fall back to Python UDFs with the clear
  warning and produce IDENTICAL results on the probe set.
- Full gate 2832/2832 on the new pin + browser suites (wasm-demo
  playground/web-component/CMS specs, cql-clinic lessons — vite `--force`).
- If duckdb-wasm must bump to get the new engine, revalidate emsdk and
  retest both browser apps; record any emsdk pin change side-by-side.

## Pressure-Test Remediation (bug_fix workflow)

Seed these as BUGFIX issues (status CONFIRMED for F1, OPEN for the rest)
before the Remediation Engineer runs. Each fix requires the reproducer AND
the full master gate. Where the pressure-test suggests a code-vs-docs
decision, the decision is noted — do not re-litigate without evidence.
(F2 is NOT seeded — adjudicated NOT A BUG above; skip it entirely.)

### Confirmed bugs (fix in code)

**F1 — CloudCredentials S3 broken (HIGH).**
`fhir4ds/sources/filesystem.py` `_ALLOWED_SECRET_OPTIONS["S3"]` accepts
`access_key_id`/`secret_access_key` but `configure()` interpolates them
verbatim into `CREATE SECRET (TYPE S3, ...)`; DuckDB 1.5.x expects
`KEY_ID`/`SECRET`, so S3 auth is impossible via the public API
(BinderException: Unknown parameter 'access_key_id'). Fix at SQL-build
time: map `access_key_id→KEY_ID`, `secret_access_key→SECRET`,
`session_token→SESSION_TOKEN` (keep accepting the documented names; keep
`region`, `endpoint_url`, `url_style`, `use_ssl` pass-through). Verify
against the DuckDB version we upgrade to (secret option names can drift
across versions — re-verify post-upgrade, and check AZURE/GCS option
names against the new DuckDB too). Add focused injection tests per the
AGENTS.md source-adapter doctrine.

**F2 — `Patient.active is Boolean` → false — ADJUDICATED NOT A BUG (do not
"fix").** The pressure-test expected true (FHIR.boolean <: System.Boolean
subtype walk). The official R4 fixtures pin the OPPOSITE:
`tests-fhir-r4.xml` testType12 `Patient.active.is(Boolean).not()` → true
and testType14 `Patient.active.is(System.Boolean).not()` → true — i.e.
`is Boolean` / `is System.Boolean` over FHIR.boolean data is FALSE by
fixture mandate. This is the documented FP-02 EXPLORER "FHIR-vs-System
namespace split" doctrine (also pinned by testType11/13: `is(boolean)` /
`is(FHIR.boolean)` → true — exact-type only). Per GLOBAL_RULES, fixtures
outrank prose and the pressure-test's hierarchy reading. Action: NO code
change. Verify our two engines already match (conformance 935/935 includes
these fixtures — if green, nothing to do); document the FHIR-vs-System
`is` doctrine in the FHIRPath docs/AGENTS NOT A BUG registry if not
already there, and note it in the release notes as pressure-test
feedback addressed-by-citation.

### Silent-wrong-answer guardrails

**U1 — Unknown resource type in CQL retrieve → silent False (HIGH).**
`exists [NotAResource]` evaluates False for every patient with no error —
a silent empty denominator. Fix: validate retrieve resource types at
TRANSLATION time against the model registry (`schema.resources.keys()` /
FHIRSchemaRegistry — NOT a hardcoded list, per the externalization
doctrine); unknown type → typed TranslationError naming the retrieve.
Watch DQM: every CMS measure retrieve must still translate (run the DQM
gate). Parameterized/profiled retrieves (`[Observation: profile]`) and
QICore-typed retrieves must keep working.

**U2 — Unresolved ValueSet → silent False/empty (HIGH).**
Two parts: (a) at evaluation setup, WARN (logging, once per library) when
a declared valueset URL resolves to zero codes — the current translator
empty-ValueSet path flattens membership to False; keep runtime behavior
unchanged (warn, not raise — historical/optional terminology loads must
not break measures). (b) Document the required `valueset_cache` format in
the DQM/terminology docs — the correct shape is `{url: iterable of codes
or (system, code) pairs}`; ALSO make bare-string code entries WORK (accept
`['a','b']` as codes with null/systemless membership) rather than silently
yielding all-False — this is the natural reading and the fix is small.
Add tests for both the warn path and the bare-string cache path.

**U3 — Bad Measure criteria name → misleading Catalog Error (MEDIUM).**
Validate population criteria names against the parsed library's
definitions BEFORE execution; unknown name → typed DQMError/ValueError
listing the definition names available. Keep the failure loud (it already
fails — just make the message point at the library, not DuckDB internals).

### Doc/behavior mismatches (docs fixes; behavior verified intentional)

Fix in docs during `bug_fix` or `docs_audit` (single pass, no behavior
changes): D1 `evaluate_measure` returns a pandas DataFrame (fix the
Relation claim + quickstart `.df()` calls); D2 `strict_mode=True` requires
a model dict (doc example must pass `model=...`); D3 `create_connection
(**kwargs)` routes kwargs as DuckDB CONFIG options (say so; note
`read_only=True`/`config={...}` are not supported — `threads=2` works);
D4 FileSystemSource raw-FHIR NDJSON derives the schema (document patient_ref
derivation: Patient id / subject refs; Group refs → NULL); D5
`parse_library` rejects non-SQLQuery/SQLView canonicals (fix the
"falls back" claim); D6 `SQLGenerator(dialect=...)` accepts only `'duckdb'`;
D7 `in_valueset` requires root-relative paths — document, and note the
inconsistency with `fhirpath()` as a known limitation; D8 remove the stale
"resource will be modified" docstring claim on `evaluate()`. Also
consider one-liner notes for: `today() <= now()` empty (precision-ambiguity
doctrine), `translate_cql` requires a full library declaration, cloud-URI
warning fires at `register()` not construction.

## Evolution Campaign (after upgrade + fixes — validates both)

36 iterations: every domain 1–12 (SPEC_QA_DOMAINS.md) receives SKEPTIC →
HISTORIAN → EXPLORER in order (iterations 1-3 = domain 1, 4-6 = domain 2,
… 34-36 = domain 12). Requested config:

- `min_iterations`: 36
- `max_iterations`: 45
- `exhaustive_mode`: false
- `target_version`: `0.0.15`
- `qa_schedule`: `[{iteration: i, domain: ceil(i/3), personality:
  [SKEPTIC, HISTORIAN, EXPLORER][(i-1) % 3]} for i in 1..36]`

Campaign-specific emphasis (supplements the catalog, does not replace it):

- **Domains 1–2 (FHIRPath)**: re-verify on the NEW DuckDB build; include
  the F2 FHIR-vs-System `is` doctrine pins (testType11-14) in probing
  (engine + native parity must hold — no behavior change).
- **Domain 3–4 (CQL/eCQM)**: hunt NEW gaps — do not re-confirm old pins;
  include U1 retrieve validation and U2 valueset-warning behavior.
- **Domain 5 (ViewDef)**: generator output correctness on the new DuckDB
  (planner changes can alter generated-SQL behavior).
- **Domains 6–10**: standard catalog; Domain 6 includes F1 (S3 secret
  creation against the new DuckDB — without real credentials, assert the
  SECRET is created and the error taxonomy for bad options); Domain 7
  re-baselines scale numbers on the new DuckDB; Domain 10 verifies the
  upgraded pin end-to-end (clean install, extension load, version triple
  consistency pyproject == submodules == loader gates).
- **Domain 11 (API surface)**: re-run the pressure-test's own checks as a
  regression battery — the t01–t12 expectations in
  /mnt/d/fhir4ds-test/ are the reference; every pressure-test PASS must
  stay a PASS and every fixed FAIL must now PASS.
- **Domain 12 (medterm4ds)**: standard integration re-verification on the
  new DuckDB (no version bump).

## Code Review (after evolution)

Standard `ROLE_CODE_REVIEWER.md` audit of the full 0.0.15 diff (DuckDB
upgrade + pressure-test fixes + campaign fixes). Carry the open REV ledger
forward (REV-002/003/005/009..019) — re-verify status, don't re-litigate
settled doctrine. Clobber spot-check the pressure-test fix symbols
(S3 KEY_ID/SECRET mapping, FHIR→System type bridge, retrieve validation,
valueset zero-code warning, criteria-name validation) and the upgrade's
version-triple consistency. Verify extension binaries md5
repo == site-packages == wheel == web deployments.

## Release Prep (pre_release)

Per `ROLE_RELEASE_ENGINEER.md`:
- Bump `pyproject.toml` 0.0.14 → 0.0.15 (root `__version__` + all 6
  subpackage constants; `test_public_subpackage_versions_match_root`
  enforces).
- `duckdb==<new pin>` exact in pyproject; wheel bundles BOTH rebuilt
  extensions; `pip check` clean; fresh-install smoke (3.10 AND 3.11).
- medterm4ds bound `>=0.0.4,<0.0.5` verified in wheel METADATA on both
  extras.
- Conformance gate 2832/2832 from a clean environment on the NEW pin
  (PYTHONPATH=/mnt/d/fhir4ds for repo runs).
- Extension binaries md5-verified repo == site-packages == wheel contents.
- Both CI matrix legs (3.10/3.11) green before sign-off.

## Documentation Updates (docs_audit)

Per `ROLE_DOCS_AUDITOR.md`, `target_version` 0.0.15:
- All DuckDB version references across README/docs/AGENTS doctrine
  (wasm-engine.md, install docs) move to the new pin.
- The D1–D8 pressure-test doc fixes land here if not already done in
  bug_fix (single source — verify no drift between the two passes).
- Draft the **v0.0.15 Release Notes**: DuckDB upgrade (version, motivation,
  single-pin doctrine note), pressure-test remediation (F1/U1–U3; F2
  addressed-by-citation with the testType12/14 fixture pins), campaign
  hardening results.
- Website per `web/website/AGENTS.md`: homepage `PRODUCT_VERSION`,
  `demo.spec.ts`, install snippets, releases.md v0.0.15 section (keep
  earlier sections), bundle the 0.0.15 wheel under `web/wasm-demo/public/`
  (remove 0.0.14), rebuild wasm-demo, copy `dist/` to
  `web/website/static/wasm-app/`, `npm run typecheck` + `npm run build`.
  Micropip `deps=False` rule is load-bearing — do not regress. Refresh
  cql-clinic bundle if its wheel/extensions changed (`npm run build` in
  `web/cql-clinic`, copy dist to `static/cql-clinic-app/`).

## Scribe

Concise commit message(s) for the 0.0.15 work from ARCHIVE_LOG.md /
GLOBAL_KNOWLEDGE.md. (Drafts only — Joel commits.)

## Focus Areas (cross-cutting)

- **Non-regression gate**: `PYTHONPATH=/mnt/d/fhir4ds
  conformance/scripts/run_all.py` → 2832/2832 (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47) on the NEW DuckDB pin. Every fix passes the reproducer
  AND the gate. DQM measure ERRORs get one retry (REV-009 doctrine).
- **Fix root causes** — no workaround shims (GLOBAL_RULES). F1 maps names
  at the SQL boundary (public API unchanged); F2 adds the spec hierarchy
  bridge rather than special-casing Boolean.
- **Fixtures outrank prose** — F2 adjudicates against tests-fhir-r4.xml
  before any change; a fixture-pinned divergence from the pressure-test's
  expectation is logged NOT A BUG with the citation, not "fixed".
- **Single-writer discipline**; no commits at any pipeline step (Joel
  commits); validation context per PROC_VALIDATION.md (PYTHONPATH rule,
  filtered output, fresh runs).
- **Ordering discipline**: the DuckDB upgrade lands BEFORE the campaign so
  all 36 iterations validate the new pin; pressure-test fixes land BEFORE
  the campaign so Domains 2/3/4/11 re-verify them in the wild.
- **Dual-Python awareness**: CI runs 3.10 AND 3.11; any version-sensitive
  behavior probed on both.
