# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Prepare and ship **fhir4ds-v2 0.0.13**. Drive a focused evolution QA campaign
over infrastructure domains 6-10 (Data Ingestion/Schema, Performance/Scale,
Error Handling/API Contract, Audit Evidence/DQM, Installation/Environment)
plus the two campaign tracks — **API surface contract testing** and
**medterm4ds integration** — then carry the findings through code review,
release prep, and documentation updates including the release info for the
website.

0.0.13 is a **release vehicle for three bodies of work**:
1. **medterm4ds 0.0.3 integration** — bump the bounded dependency from
   `>=0.0.2,<0.0.3` to `>=0.0.3,<0.0.4` on both extras, install 0.0.3 into
   the environment, and re-verify the full integration surface against the
   new version.
2. **Post-0.0.12 reliability fixes** already on dev (commit 4f7de65b):
   orjson 3.12 deep-nesting compatibility (error-message match in
   `_parse_json`), DQM evaluator numpy-safe population truthiness, DQM CLI
   parameter filtering to library-declared names, recursion-limit import
   leak fix (test CLI + run_dqm), httpx in the dev extra. The published
   0.0.12 wheel carries the orjson 3.12 breakage — 0.0.13 is the patch.
3. **A fresh evolution QA campaign** (21 iterations, same structure as the
   0.0.12 campaign) to harden the tree before the bump.

Non-regression on the 2832-test master gate is a hard constraint throughout.

## Target Version

**0.0.13** (current `pyproject.toml` version is 0.0.12; the Release Engineer
performs the bump). Release date: not pinned — date the release notes at
prep time.

## Pipeline

1. `evolution` (21 QA iterations minimum)
2. `code_review`
3. `pre_release`
4. `docs_audit`
5. `scribe`

## Evolution Campaign

Run each of the 7 tracks below exactly three times, one pass per personality
(SKEPTIC, HISTORIAN, EXPLORER), sequentially: 21 iterations minimum.
Requested configuration:

- `min_iterations`: 21
- `max_iterations`: 30
- `exhaustive_mode`: false
- `target_version`: `0.0.13`
- `qa_schedule`: domains in order **6, 7, 8, 9, 10, 11, 12**, each receiving
  SKEPTIC → HISTORIAN → EXPLORER (i.e. iterations 1-3 = domain 6, 4-6 =
  domain 7, ... 16-18 = domain 11, 19-21 = domain 12)

### Tracks (all 12 domains per SPEC_QA_DOMAINS.md; the campaign-specific detail below supplements the catalog entries)

**Domain 6 — Data Ingestion and Schema** (FHIRDataLoader, resources table):
re-verify the 0.0.12 loader doctrine under new attack: Patient-typed
patient_ref attribution (loader + FileSystemSource), versioned-ref resolve,
BOM/case-insensitive directory handling, per-entry bundle validation,
Arrow bulk path correctness under pathological shapes. Hunt for regressions
and NEW gaps, not re-confirmations.

**Domain 7 — Performance and Scale**: 1k/10k/50k synthetic patients, memory
leak detection (tracemalloc), concurrent connection pooling. Hunt Scaling
Cliffs (super-linear slowdown) and memory spikes — do NOT flag linear
slowdown as a bug. Verify the Arrow bulk path still delivers ~70-150x vs
executemany and that the dedup semi-join holds at 50k.

**Domain 8 — Error Handling, Robustness, API Contract**: actionable errors
vs internal SQL leaks, typed exceptions (no bare `Exception`), closed
connections, invalid JSON. Re-verify the 0.0.12 boundary guards
(output_columns/parameters validation, parameters dict type guard) and the
adjudicated bare-connection doctrine (missing-UDF catalog errors surface raw
by design — controlling test
`test_evaluate_measure_missing_udf_catalog_error_is_not_rewritten`).

**Domain 9 — Audit Evidence and DQM**: human-readable evidence tied to
resource IDs, correct evidence for exclusion/exception populations, causal
correctness. Regression-verify the 0.0.12 fixes hold: MT-008 Min/Max
arg_min/arg_max attribution (e2e evidence names the winning resource),
Quantity result typing through CTE references, one-row-per-patient audit
output, numpy-safe population masks on both old and new numpy.

**Domain 10 — Installation and Environment**: clean install/import, C++
extension load vs Python fallback (no silent fallback — verify the
unsigned-dev-build WARNING still surfaces), `__version__` consistency
(pyproject + root + all 6 subpackage constants), `pip check`, idempotency of
`register(con)`. Include a **dual-Python validation**: the CI matrix runs
3.10 AND 3.11 — a 3.11 venv exists at /tmp/py311env (or recreate with
`uv venv --python 3.11`); run the CI pytest invocation on both before
release.

**Domain 11 — API Surface Contract Testing** (campaign track): exercise
every documented public entry point as an API consumer, asserting the
documented contract (types in/out, error taxonomy, idempotency):
`fhir4ds.create_connection` / `fhir4ds.register`, `fhir4ds.cql.translate_cql`
/ `translate_library_to_sql` / `evaluate_measure`,
`fhir4ds.viewdef.parse_view_definition` / `generate_view_sql`,
`fhir4ds.sqlquery.parse_library` / `parse_sqlquery` / `parse_sqlview` /
`SQLQueryRunner`, `fhir4ds.fhirpath.evaluate`, terminology factory
(`fhir4ds.cql.terminology.factory` — env-var modes, error surfaces), the
notes pipeline (`fhir4ds.cql.loader.NotesPipeline`), and `fhir4ds.dqm`
orchestration entry points. Verify signatures against the docs/README
examples — flag any drift between documented and actual behavior.

**Domain 12 — medterm4ds Integration** (campaign track): the full
fhir4ds↔medterm4ds integration surface **upgraded to medterm4ds 0.0.3**.
FIRST ACTION: `pip install medterm4ds==0.0.3` into the environment (0.0.2 is
currently installed; 0.0.3 is on PyPI), then diff-audit the 0.0.2→0.0.3
surface before trusting any adapter behavior. Then re-verify: adapters and
factory (connect error contract, cache_indexes, env-var modes), the
bounded-version contract (`>=0.0.3,<0.0.4` on both `terminology` and `ner`
extras — verify the bound is what actually ships), ValueSet expansion paths
(active-only vs include-retired policy split), code search — HTTP +
in-process `$search` (`search_text`/`search_batch`: system mapping,
searchMode lexical/hybrid/semantic, count semantics), annotation —
`auto_coder` (match grades, the fhir4ds match-grade extension,
userSelected=false), and the NER notes pipeline (extract kwargs:
mode/min_grade/include_*; disambiguation + blocklist behavior — re-derive
from the 0.0.3 source, do not assume 0.0.2 behavior). Env-gated live HTTP
tests (`MEDTERM4DS_TEST_URL`) skip-note without a sidecar.

## Code Review (after evolution)

Standard `ROLE_CODE_REVIEWER.md` audit of the full 0.0.13 diff (post-0.0.12
reliability fixes + medterm4ds 0.0.3 bump + this evolution's fixes). Carry
the open REV ledger forward (REV-002/003/005/009..016 from the
spec-compliance milestones) — re-verify status, don't re-litigate settled
doctrine. Clobber spot-check key fix symbols before sign-off, including the
post-release fixes (orjson message match, numpy-safe `_truthy`,
`_declared_parameters_only`).

## Release Prep (pre_release)

Per `ROLE_RELEASE_ENGINEER.md`:
- Bump `pyproject.toml` 0.0.12 → 0.0.13 (plus root `__version__` and all 6
  subpackage version constants — `test_public_subpackage_versions_match_root`
  enforces it).
- Build the wheel; verify the medterm4ds bound (`>=0.0.3,<0.0.4`) ships in
  metadata on BOTH extras; `pip check` clean; fresh-install smoke test.
- Conformance gate 2832/2832 from a clean environment (PYTHONPATH=/mnt/d/fhir4ds
  for repo runs).
- Extension binaries md5-verified repo == site-packages == wheel contents.
- Run the CI pytest invocation on Python 3.10 AND 3.11 (fresh orjson 3.12)
  before sign-off — both matrix legs must be green.

## Documentation Updates (docs_audit) — including website release info

Per `ROLE_DOCS_AUDITOR.md`, `target_version` 0.0.13:
- README/docs version references; `%pip install` snippets point at 0.0.13.
- Draft the **v0.0.13 Release Notes** (date at prep time). Content pillars:
  post-0.0.12 reliability fixes (orjson 3.12 deep-nesting compatibility,
  DQM numpy-safe population evaluation, CLI parameter validation),
  medterm4ds 0.0.3 integration (bounded dep bump, re-verified search/
  expansion/annotation surface), and this campaign's hardening results.
- **Website release info** — follow `web/website/AGENTS.md` exactly: update
  homepage `PRODUCT_VERSION`, `web/website/tests/demo.spec.ts`, install
  snippets, add the v0.0.13 section to `docs/getting-started/releases.md`
  (keep 0.0.12 and earlier sections), bundle the new 0.0.13 wheel under
  `web/wasm-demo/public/` (remove the 0.0.12 wheel), rebuild
  `web/wasm-demo`, copy `dist/` into `web/website/static/wasm-app/`, then
  `npm run typecheck` and `npm run build` in `web/website`. The micropip
  `deps=False` snippet rule in that AGENTS.md is load-bearing — do not
  regress it.

## Scribe

Concise commit message(s) summarizing the 0.0.13 work from ARCHIVE_LOG.md /
GLOBAL_KNOWLEDGE.md. (Scribe drafts only — Joel commits.)

## Focus Areas (cross-cutting)

- **Non-regression gate**: `PYTHONPATH=/mnt/d/fhir4ds conformance/scripts/run_all.py`
  → 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47). Every fix
  passes the reproducer AND the gate. DQM measure ERRORs get one retry
  (REV-009 doctrine, now terminal-unconfirmed).
- **Fix root causes** — no workaround shims, no hint wrappers (GLOBAL_RULES).
- **Single-writer discipline** — never rewrite files from stale copies.
- **No commits** at any pipeline step; Joel reviews and commits.
- **Validation context discipline** per PROC_VALIDATION.md — filtered output,
  PYTHONPATH rule, fresh runs only.
- **Dual-Python awareness**: local 3.10 env may carry older transitive deps
  (orjson 3.11.9); CI resolves fresh (orjson 3.12, Python 3.11). Any
  string-match on third-party messages or version-sensitive behavior must
  be probed on both. NOTE (pre-campaign, for Joel): GitHub Actions has not
  queued a run for dev commit 4f7de65b — verify Actions minutes/billing
  before relying on CI as the green signal; local dual-Python runs are the
  authoritative gate meanwhile.
