# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Prepare and ship **fhir4ds-v2 0.0.12**. Drive a focused evolution QA campaign
over infrastructure domains 6-10 (Data Ingestion/Schema, Performance/Scale,
Error Handling/API Contract, Audit Evidence/DQM, Installation/Environment)
plus two campaign-specific tracks — **API surface contract testing** and
**code search/annotation functionality** — then carry the findings through
code review, release prep, and documentation updates including the release
info for the website.

The tree already carries two uncommitted bodies of work this release ships:
the completed 58-chunk SQL-on-FHIR/CQL/FHIRPath spec-compliance campaign and
the medterm4ds 0.0.2 integration. The 0.0.12 release is the vehicle for both.
Non-regression on the 2832-test master gate is a hard constraint throughout.

## Target Version

**0.0.12** (current `pyproject.toml` version is 0.0.11; the Release Engineer
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
- `target_version`: `0.0.12`
- `qa_schedule`: domains in order **6, 7, 8, 9, 10, 11, 12**, each receiving
  SKEPTIC → HISTORIAN → EXPLORER (i.e. iterations 1-3 = domain 6, 4-6 =
  domain 7, ... 16-18 = domain 11, 19-21 = domain 12)

### Tracks (all 12 domains per SPEC_QA_DOMAINS.md — domains 11-12 were added to the catalog for this campaign; the campaign-specific detail below supplements the catalog entries)

**Domain 6 — Data Ingestion and Schema** (FHIRDataLoader, resources table):
bundles (transaction/batch/collection), NDJSON, line-level error propagation,
malformed-but-valid-JSON, missing `resourceType`, duplicate IDs, >1MB
resources. Key question: does subtly-malformed input validate, silently
ingest, or crash?

**Domain 7 — Performance and Scale**: 1k/10k/50k synthetic patients, memory
leak detection (tracemalloc), concurrent connection pooling. Hunt Scaling
Cliffs (super-linear slowdown) and memory spikes — do NOT flag linear
slowdown as a bug.

**Domain 8 — Error Handling, Robustness, API Contract**: actionable errors
vs internal SQL leaks, typed exceptions (no bare `Exception`), closed
connections, invalid JSON. Key question: are error messages actionable?

**Domain 9 — Audit Evidence and DQM**: human-readable evidence tied to
resource IDs, correct evidence for exclusion/exception populations, causal
correctness. Key question: does the audit trail explain WHY a patient was
included/excluded, or just report outcomes?
**Known open issue to triage early (iteration for domain 9, first action):**
`fhir4ds/cql/tests/unit/test_audit_mode.py::TestMinMaxAttribution`
(test_min/test_max on query sources) fails on the current tree — translator
emits no `arg_min`/`arg_max` for query-level Min/Max attribution (logged as
MT-008 during the medterm integration; proven unrelated to terminology).
Root-cause and fix under this domain.

**Domain 10 — Installation and Environment**: clean install/import, C++
extension load vs Python fallback (no silent fallback — the SOF-VD-11 fix
added a WARNING; verify it surfaces), `__version__` consistency, `pip check`,
idempotency of `register(con)`.

**Domain 11 — API Surface Contract Testing** (campaign track): exercise
every documented public entry point as an API consumer, asserting the
documented contract (types in/out, error taxonomy, idempotency):
`fhir4ds.connect`/`fhir4ds.cql.translate_cql` /
`translate_library_to_population_sql` / `evaluate_measure`,
`fhir4ds.viewdef.parse_view_definition` / `generate_view_sql` / runner APIs
(`fhir4ds.viewdef` materialization), `fhir4ds.sqlquery.parse_library` /
`parse_sqlquery` / `parse_sqlview` / `SQLQueryRunner`,
`fhir4ds.fhirpath.evaluate` / `fhirpath_is_valid`, terminology factory
(`fhir4ds.cql.terminology.factory` — env-var modes, error surfaces), the
notes pipeline (`fhir4ds.cql.loader.NotesPipeline` or equivalent), and
`fhir4ds.dqm` orchestration entry points. Verify signatures against the
docs/README examples — flag any drift between documented and actual behavior.

**Domain 12 — medterm4ds Integration** (campaign track): the full
fhir4ds↔medterm4ds integration surface — adapters and factory (connect error
contract, cache_indexes, env-var modes), the bounded-version contract
(`>=0.0.2,<0.0.3` on both `terminology` and `ner` extras — verify the bound
is what actually ships), ValueSet expansion paths (active-only vs
include-retired policy split from the medterm 0.0.2 integration), code
search — HTTP + in-process `$search` (`search_text`/`search_batch`: system
mapping, searchMode lexical/hybrid/semantic, count semantics), annotation —
`auto_coder` (match grades, the fhir4ds match-grade extension,
userSelected=false), and the NER notes pipeline (extract kwargs:
mode/min_grade/include_*; medterm 0.0.2 three-signal disambiguation +
blocklist behavior). Test against installed medterm4ds 0.0.2 (already in
the env — do not reinstall). Env-gated live HTTP tests
(`MEDTERM4DS_TEST_URL`) skip-note without a sidecar.

## Code Review (after evolution)

Standard `ROLE_CODE_REVIEWER.md` audit of the full 0.0.12 diff (campaign +
medterm integration + this evolution's fixes). Carry the open REV ledger
(REV-002..016 from the spec-compliance milestone reviews, REV-001 from the
medterm review) forward — re-verify status, don't re-litigate settled
doctrine. Clobber spot-check key fix symbols before sign-off.

## Release Prep (pre_release)

Per `ROLE_RELEASE_ENGINEER.md`:
- Bump `pyproject.toml` 0.0.11 → 0.0.12.
- Build the wheel; verify the medterm4ds bound (`>=0.0.2,<0.0.3`) ships in
  metadata; `pip check` clean; fresh-install smoke test.
- Conformance gate 2832/2832 from a clean environment (PYTHONPATH=/mnt/d/fhir4ds
  for repo runs).
- Extension binaries md5-verified repo == site-packages == wheel contents.

## Documentation Updates (docs_audit) — including website release info

Per `ROLE_DOCS_AUDITOR.md`, `target_version` 0.0.12:
- README/docs version references; `%pip install` snippets point at 0.0.12.
- Draft the **v0.0.12 Release Notes** (date at prep time). Content pillars:
  SQL-on-FHIR v2 spec-compliance campaign results (ViewDefinition +
  Analytics Layer hardening), CQL translator fixes (exact-Decimal arithmetic,
  age-uncertainty semantics, list/aggregate correctness), FHIRPath dual-engine
  parity work, medterm4ds 0.0.2 integration (bounded dep, retired-code
  policy, in-process intensional expansion).
- **Website release info** — follow `web/website/AGENTS.md` exactly: update
  homepage `PRODUCT_VERSION`, `web/website/tests/demo.spec.ts`, install
  snippets, `docs/getting-started/releases.md`, bundle the new 0.0.12 wheel
  under `web/wasm-demo/public/`, rebuild `web/wasm-demo`, copy `dist/` into
  `static/wasm-app/`, then `npm run typecheck` and `npm run build` in
  `web/website`. The micropip `deps=False` snippet rule in that AGENTS.md is
  load-bearing — do not regress it.

## Scribe

Concise commit message(s) summarizing the 0.0.12 work from ARCHIVE_LOG.md /
GLOBAL_KNOWLEDGE.md. (Scribe drafts only — Joel commits.)

## Focus Areas (cross-cutting)

- **Non-regression gate**: `PYTHONPATH=/mnt/d/fhir4ds conformance/scripts/run_all.py`
  → 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47). Every fix
  passes the reproducer AND the gate. DQM measure ERRORs get one retry
  (REV-009 doctrine, now terminal-unconfirmed).
- **Fix root causes** — no workaround shims, no hint wrappers (GLOBAL_RULES).
- **Single-writer discipline** — the tree carries large uncommitted work;
  never rewrite files from stale copies.
- **No commits** at any pipeline step; Joel reviews and commits.
- **Validation context discipline** per PROC_VALIDATION.md — filtered output,
  PYTHONPATH rule, fresh runs only.
