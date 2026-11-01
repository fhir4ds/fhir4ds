# Engineer Handoff — medterm4ds 0.0.2 remediation (bug_fix, 2026-08-24)

Workflow: `bug_fix`, iteration 1. All scoped issues MT-001..MT-007 RESOLVED.
exit_reason CLEAN; workflow set to null. One out-of-scope discovery logged
as MT-008 (NEW, pre-existing campaign-tree failure).

## Environment

```
$ pip show medterm4ds
Name: medterm4ds
Version: 0.0.2
```
(Not reinstalled/upgraded, per constraints.)

## Per-issue outcomes

- **MT-001 RESOLVED** — `pyproject.toml` terminology extra:
  `medterm4ds>=0.0.1` → `medterm4ds>=0.0.2,<0.0.3`, with a comment
  explaining the silent-minor-bump incident. (`ner` extra's
  `medterm4ds[extraction]` left as-is — directive scoped line 57 only.)
- **MT-002 RESOLVED** — `http_adapter.search_text` now sends
  `{query, system, searchMode, count:"25"}`. category→system via new
  shared `system_mappings.category_to_system_param()` (canonical URLs,
  comma-joined); unknown/empty category omits `system` (all-systems).
  Legacy `category`/`mode` params removed.
- **MT-003 RESOLVED** — `expand()` GET adds `count=1000,
  activeOnly="false"`; `expand_intensional()` POST adds the same.
- **MT-004 RESOLVED** — `in_process_adapter.expand` primary path is
  `apps.fhir_api.expand_url_pattern(engine, url, count=1000,
  include_retired=True)`; facade `Terminology.expand_url` retained as
  fallback (no include_retired — documented degradation).
- **MT-005 RESOLVED** — `expand_intensional` wired:
  `expand_intensional_value_set(engine, vs, 1000, include_retired=True)`
  (count POSITIONAL) primary; facade
  `Terminology.expand_intensional(vs, count=1000)` fallback. Protocol
  signature unchanged.
- **MT-006 RESOLVED** — `connect()` RuntimeError caught and re-raised
  with a hint naming `FHIR4DS_TERMINOLOGY_DB` and remediations
  (build-duckdb / omit db_path / prepare-derived for schema 0.9).
  `cache_indexes=True` passed (with inner TypeError retry without it for
  drift). `search_index_dir` DEBUG-logged when unused; still honored on
  the legacy TypeError fallback path only.
- **MT-007 RESOLVED** — tests updated/added (see below); fake audit
  clean (test_plumbing_terminology / test_resolver_fallback /
  loader.test_auto_coder fakes are protocol-level, no stale HTTP param
  dicts).

## Validation (blocker gates)

- **Master gate**: `PYTHONPATH=/mnt/d/fhir4ds conformance/scripts/run_all.py`
  → ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  **OVERALL 2832/2832 (100%)**. HELD.
- **medterm integration**: `test_medterm4ds_in_process.py` → 4/4 passed
  (against installed 0.0.2, default discovery fixture).
- **medterm live**: `test_medterm4ds_live.py` → 4 skipped
  (MEDTERM4DS_TEST_URL unset — no sidecar). SKIP-NOTED.
- **Unit suites**: terminology 99 passed; plumbing/resolver/auto_coder/
  fhir_server 52 passed; loader (incl. notes pipeline, behavioral only)
  216 passed.
- **Known unrelated failures**: `test_audit_mode.py
  TestMinMaxAttribution::test_min/max_on_query_uses_arg_min/max` fail
  (2 of 1623) — pre-existing on the uncommitted campaign tree
  (translator arg_min/arg_max attribution), reproduced in a
  terminology-free subprocess env. Logged MT-008; not touched
  (single-writer discipline).

## Spot-check evidence

- `connect('/nonexistent/mt.db')` (live, real medterm4ds 0.0.2) →
  `RuntimeError: medterm4ds terminology database unavailable: Database
  not found: /nonexistent/mt.db. … FHIR4DS_TERMINOLOGY_DB … build one
  with 'medterm4ds data build-duckdb' …` (hint chain present).
- HTTP `$search` mocked-client capture:
  `{'query': 'diabetes', 'system': 'http://snomed.info/sct',
  'searchMode': 'hybrid', 'count': '25'}` for category="condition";
  unknown/"" category → no `system` key; legacy keys absent.
- `category_to_system_param`: condition→`http://snomed.info/sct`,
  medication→rxnorm URL, unknown→None (verified live).
- HTTP `$expand` capture: `{'url': …, 'count': 1000, 'activeOnly':
  'false'}`; intensional POST `{'count': 1000, 'activeOnly': 'false'}`.
- In-process include_retired: `expand_url_pattern.assert_called_once_with(
  engine, url, count=1000, include_retired=True)` and facade
  `expand_url.assert_not_called()`; intensional called with positional
  `1000` + `include_retired=True`.

## Files changed

Code:
- `pyproject.toml` (dep bound)
- `fhir4ds/cql/terminology/http_adapter.py` ($search/$expand params)
- `fhir4ds/cql/terminology/in_process_adapter.py` (connect hardening,
  expand preference flip, intensional wiring, shared mapping aliases)
- `fhir4ds/cql/terminology/system_mappings.py` (CATEGORY_TO_SOURCES +
  category_to_source_mnemonics + category_to_system_param)

Tests:
- `fhir4ds/cql/tests/unit/terminology/test_http_adapter.py`
- `fhir4ds/cql/tests/unit/terminology/test_in_process_adapter.py`

Bookkeeping:
- `fhir4ds/cql/AGENTS.md` (remediation section + fragile-area note)
- `evolution.json` (issues RESOLVED w/ verified_in; MT-008 NEW)

## No regressions, no shims; settled decisions honored
Retired-policy split (include-retired expansion/membership; active-only
search), dep bound, intensional wiring, full test scope — implemented
exactly as directed. No commits/pushes made.
