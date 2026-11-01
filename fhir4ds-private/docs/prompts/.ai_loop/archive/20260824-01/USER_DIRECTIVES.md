# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI running the loop.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Integrate fhir4ds with **medterm4ds 0.0.2** (published; the dependency was
unbounded so behavior changed under us). Bound the dependency, fix the HTTP
adapter's long-broken `$search`/`$expand` parameters, harden `connect()`
failure handling, adopt an explicit retired-code policy, and wire in-process
intensional expansion.

The work is **scoped to the issue list below**. Anything not listed is out of
scope. Non-regression on the 2832-test master gate plus the medterm
integration suites is a hard constraint.

## Decisions already settled with Joel (2026-08-24) — do NOT re-litigate

1. **Retired codes split by use-site**: include-retired on expansion /
   membership paths (CQL `in ValueSet` resolution, terminology_closure —
   historical patient data carries codes retired since recording);
   active-only on search/autocoding paths.
2. **Dependency bound**: `medterm4ds>=0.0.2,<0.0.3`.
3. **Wire `expand_intensional` in-process now** (0.0.2 exposes it on the
   public Python API).
4. **Full test scope**: adapters + notes-pipeline tests against installed
   0.0.2 (already installed in this environment — verify with
   `pip show medterm4ds`).

## Pipeline

1. `bug_fix` — Remediation Engineer addresses the seeded issues MT-001..MT-007
2. `code_review` — Code Reviewer re-audits the diff

Skip `feature_design` — fixes are precisely specified below.

## medterm4ds 0.0.2 API facts (verified against the v0.0.2 tag at
/mnt/d/medterm4ds — trust these, do not re-derive)

- `connect(db_path=None, *, ..., read_only=True, prepare_cache=False,
  cache_sources=None, cache_indexes=False, ...)` — client.py:743.
  db_path set but missing → **RuntimeError** with a build hint.
  `cache_indexes` default False. **No `search_index_dir` param.**
- Facade `Terminology.expand_url(url, *, count=1000) -> list[CodeRef]` —
  **NO include_retired**; CodeRef carries source+code only (display unset).
- `apps.fhir_api.expand_url_pattern(engine, url, *, count=1000,
  include_retired=False) -> dict` — FHIR ValueSet payload.
- Facade `Terminology.expand_intensional(value_set, *, count=1000) ->
  list[CodeRef]` — no include_retired.
- `apps.fhir_api.expand_intensional_value_set(engine, value_set, count=1000,
  *, include_retired=False) -> (deduped, depth_cap_hit)` of
  `{"system","code","display"}` dicts — count is POSITIONAL; NOT truncated.
- HTTP `$search`: params `query` (required), `system`, `searchMode`
  (lexical|hybrid|semantic|canonical, default lexical), `count` (1-200),
  `resultTypes`. Our old `category`/`mode` params were silently dropped.
- HTTP `$expand`: `url`, `count` (default 20, max 1000), `activeOnly`
  (default **True** — deliberate divergence from R4; activeOnly=false
  includes retired for url/intensional, 400 for filter-based).
- `services.discovery.search_names(query, engine, *, sources=None,
  tty_filters=None, limit=25)` — unchanged for our purposes.
- Prepared schema is now **0.9**; opening an 0.0.1-provisioned DuckDB logs
  a warning and disables patient-friendly paths (no raise). Rebuild is
  Joel's ops action (`medterm4ds data prepare-derived --db <path>`) —
  document in error hints, do not run.

## Specific Bug Fix

Seven issues seeded into `evolution.json.issues[]`. Recommended order
(MT-001 first so everything lands on the bounded dep; MT-006 before MT-004/005
so connect hardening exists while you rework the paths):

### MT-001 (HIGH) — Bound the dependency

`pyproject.toml:57` `medterm4ds>=0.0.1` → `medterm4ds>=0.0.2,<0.0.3`.
Unbounded minor bumps shipped silent behavior changes (this incident);
re-verify deliberately before each bump.

### MT-002 (HIGH) — HTTP `$search` sends params medterm4ds never read

`fhir4ds/cql/terminology/http_adapter.py:459-463` sends
`{"query", "category", "mode"}`. medterm4ds has always expected
`system`/`searchMode` — FastAPI drops unknowns, so HTTP search has always
been **all-systems lexical** regardless of the `mode="hybrid"` callers
request. Fix: `{"query": query, "system": <mapped>, "searchMode": mode,
"count": 25}`. Map category→system via the existing
`_CATEGORY_TO_SOURCES`/`SOURCE_MNEMONIC_TO_URL` machinery
(in_process_adapter.py:497-517 — move to system_mappings.py to share);
unknown/empty category → omit `system` (all-systems is the medterm
semantic). `searchMode` accepts lexical|hybrid|semantic|canonical — our
default `hybrid` is valid. count 25 = parity with in-process limit.

### MT-003 (HIGH) — HTTP `$expand` silently capped at 20 codes

`http_adapter.py:398` sends no `count` → medterm default 20 vs the
in-process path's 1000; large value sets truncate invisibly (closure table
likely already incomplete via HTTP mode). Fix both `expand()` and
`expand_intensional()`: `count=1000` (max), `activeOnly=false` (expansion
feeds membership → include retired per the settled policy).

### MT-004 (MEDIUM) — In-process expansion drops retired codes under 0.0.2

`in_process_adapter.py:263-329`: the preferred facade
`Terminology.expand_url()` has no `include_retired` opt-in and 0.0.2
defaults active-only. Flip the preference: PRIMARY path becomes
`medterm4ds.apps.fhir_api.expand_url_pattern(engine, url, count=1000,
include_retired=True)` (already imported as the fallback; the existing
FHIR-payload parsing path at lines 295-329 handles its output); keep the
facade as fallback when `expand_url_pattern` is unavailable. FHIR-payload
`system` values are canonical URLs — `_normalize_system` already passes
them through correctly.

### MT-005 (MEDIUM) — Wire in-process `expand_intensional`

`in_process_adapter.py:331-362` returns `[]` with a "use HTTP mode"
warning. Replace: preferred
`medterm4ds.apps.fhir_api.expand_intensional_value_set(engine, value_set,
1000, include_retired=True)` (note: count POSITIONAL; returns dicts with
system/code/display) → convert via `_to_coderef`. Fallback: facade
`Terminology.expand_intensional(value_set, count=1000)` (CodeRefs, no
include_retired — acceptable degradation). Protocol signature unchanged;
closure.py's `is-a` filter path (closure.py:246-259) starts working
in-process again.

### MT-006 (MEDIUM) — `connect()` hardening + cache_indexes

`in_process_adapter.py:130-155`: catch `RuntimeError` from
`_m.connect(...)` → re-raise with a config hint naming
`FHIR4DS_TERMINOLOGY_DB` and remediation (build via
`medterm4ds data build-duckdb`, auto-provision by omitting db_path,
schema-0.9 rebuild via `medterm4ds data prepare-derived --db <path>`).
Pass `cache_indexes=True` (the adapter holds one long-lived engine by
design — persisting BM25 indexes matches the architecture). Keep the
existing `TypeError` fallback for older medterm. `search_index_dir`:
0.0.2 `connect()` has no such param — keep it only in the TypeError
fallback path; DEBUG-log when provided but unused. factory.py:120 leaves
adapter errors uncaught by design — the re-raised hinted RuntimeError IS
the user-facing error.

### MT-007 (MEDIUM) — Tests against 0.0.2

- Unit: new/updated tests for $search params (system mapping, searchMode,
  count), $expand count/activeOnly, RuntimeError re-raise hint,
  include_retired primary path, intensional wiring. Check the existing
  hand-rolled fakes (test_plumbing_terminology.py, test_resolver_fallback.py,
  loader/test_auto_coder.py) for stale assertions on the old param dict.
- Integration: `pytest fhir4ds/cql/tests/integration/test_medterm4ds_in_process.py`
  (its fixture uses default discovery — connect(None) auto-provisions;
  unaffected by the RuntimeError change). `test_medterm4ds_live.py` is
  env-gated (`MEDTERM4DS_TEST_URL`) — run if a sidecar is up, else note skip.
- Notes pipeline: behavioral assertions only (NO golden fixtures exist);
  if 0.0.2 extraction changes (three-signal disambiguation, blocklist)
  loosen/tighten assertions deliberately, eyeballing each diff.

## Focus Areas

- **Non-regression**: `PYTHONPATH=/mnt/d/fhir4ds conformance/scripts/run_all.py`
  → 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47). Master gate
  plus the medterm suites named in MT-007.
- **Machine-readable spec artifacts outrank prose** (GLOBAL_RULES): the 0.0.2
  signatures above were taken from the v0.0.2 tag source — trust them.
- **Single-writer discipline**: no whole-file rewrites from stale copies;
  the campaign tree carries the completed spec-compliance pass uncommitted.
- **Record in handoffs**: `pip show medterm4ds` output; spot-check evidence
  that HTTP `$search` now sends `system`/`searchMode`/`count` and that
  in-process expand includes retired codes (or documents their absence in
  the provisioned DB).

## Out of scope

- Rebuilding provisioned DuckDBs to schema 0.9 (Joel's data-ops action;
  document in hints only).
- medterm4ds 0.0.3+ (bounded out by MT-001).
- Any spec_schedule.json changes — the 58-chunk compliance pass is terminal.
