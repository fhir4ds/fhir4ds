# Code Review Findings — 0.0.15 Campaign (2026-09-20)

Scope: full uncommitted campaign diff vs HEAD `0d3fb500` (dependency_upgrade 1.5.2→1.5.5 + bug_fix F1/U1/U2/U3 + evolution iterations 1-36, QA-001..QA-024). Role: ROLE_CODE_REVIEWER.md (security & implementation audit).

## Verdict: CLEAN_WITH_NOTES

No CRITICAL or HIGH findings. Two LOW findings filed (REV-020, REV-021).

## 1. Security Audit — PASS

- **SQL injection (CloudCredentials, BUGFIX-001/F1)**: `_SECRET_OPTION_ALIASES` maps snake_case kwargs to native DuckDB 1.5.5 option names; option NAMES come from a fixed alias table (never user input); VALUES pass through `quote_sql_literal()`. Live injection probe (`access_key_id="AKI', (TYPE GCS) --"`) confirmed quote-doubling blocks injection. `secret_name` via `quote_identifier`. `PROVIDER service_principal` clause is a fixed string, not interpolated. Tests pin the quoting (test_filesystem.py injection cases retained).
- **Retrieve validation (U1)**: `TranslationError` on unknown resource types; the type set is data-driven (viewdef `KNOWN_FHIR_RESOURCE_TYPES` — 159 spec-published codes — plus schema registry keys), lazily imported to avoid a hard cql→viewdef dependency. No behavior-changing hardcoding.
- **Output-columns guard (U3)**: typed `ValueError` listing unknown + available definitions before any SQL emission.
- No new `except Exception: pass` blocks introduced anywhere in the diff (all `except Exception` sites in touched files are pre-existing, reviewed: loader macro-registration best-effort paths with named-logger diagnostics, and `_infer_cql_type` inference fallback).

## 2. Clobber Guard — PASS

All 24 campaign fix symbols verified present across 17 source files (nodes.py QA-005/006, engine/__init__ QA-007, collections.py QA-008, _operators.py QA-009/020/021, _query.py U1/QA-013/017/018/019, _lists.py QA-011/012/017, _functions.py QA-011/014/015, _utils.py QA-011/017, translator.py U3/QA-011, inference.py QA-013, cte_manager.py QA-021, parser.py QA-010, valueset.py U2, auto_coder.py QA-024, fhir_loader.py U2, udf.py QA-001, evaluator.cpp QA-003/004, fhirpath_extension.cpp QA-002, cql_extension.cpp QA-016).

## 3. Binary Freshness / Deployment — PASS

- fhirpath.duckdb_extension md5 `fd81a7c2…` repo == site-packages; binary newer than evaluator.cpp/fhirpath_extension.cpp.
- cql.duckdb_extension md5 `4e4ff1e3…` repo == site-packages; binary newer than cql_extension.cpp.
- (Supersedes the historical REV-008 drift pattern; no ~/.duckdb cache copies.)

## 4. Implementation Quality

- Native edits are minimal and doctrine-commented (empty-expression row resilience; jsonKindClass guard placed correctly AFTER the null doctrine and BEFORE scalar guards — the placement was the hard-won lesson; concat gate on fhir_type metadata only; has_time clearing for expand per-day).
- `infix_invoke` QA-007 deferred-error pattern correctly distinguishes nullable ops (empty-wins) from non-nullable (~, |, logic — empties must reach fn), preserving `{} ~ {}` = true and `1 / 'a'` inside union still aborting (FP-19 doctrine).
- With-clause QA-018 rewrite: shared scope + nested EXISTS composition; single-with emits the same flat shape (verified by unchanged tests); resource_alias save/restore in try/finally.
- Test files exist and pass: 98 (guard+filesystem+iter4) + 91 (evol regression files it1/it6/it7/it10) all green.

## 5. Findings (new)

### REV-020 (LOW, OPEN)
`CloudCredentials.configure()` (`fhir4ds/sources/filesystem.py`): non-string credential values are coerced via `str(value)` in `option_items`, so `use_ssl=True` emits `USE_SSL 'True'` (and `use_ssl=1` emits `'1'`). DuckDB 1.5.5 accepts case-insensitive boolean strings so this works today, but the rendering is provider-faithfulness luck rather than contract. Evidence: configure() probe emitted `USE_SSL 'True'`. Proposed: normalize bool → `'true'/'false'` lowercase at alias-mapping time. Not blocking.

### REV-021 (LOW, OPEN — REV-002 duplication family)
The 6-name JSON-list UDF tuple `("expand", "expand1", "expand_points", "expand_points1", "collapse_intervals", "collapse_intervals_per")` is hand-duplicated in 5+ sites: `_lists.py` (×3: two First/Last list branches + the JSON wrap), `_query.py` aggregate fold, `_functions.py` (×2: `_json_list_source_for_extract`, `_wrap_list_aggregate`/list-agg gate), `_utils.py` `_is_list_returning_sql`. The CQL-15 HISTORIAN lesson ("every new JSON-list UDF must be recognized at EVERY consumer site") makes this drift-prone. Proposed: one module-level `frozenset` (e.g. `_JSON_LIST_UDF_NAMES` in `_utils.py`) imported everywhere. Not blocking.

## 6. Carried Open Items (unchanged from prior milestones)

REV-002 (metadata duplication native/python tables), REV-003 (unrelated untracked files in tree — staging discipline), REV-005 (mid-pattern inline regex flags DeprecationWarning), REV-009 (DQM loader intermittent retry), REV-010 (shape-selection detection layer consolidation), REV-012 (Python fallback uncertain-range parser leniency), REV-014/015 (5+2 fhirpath parity residuals — note QA-001 fixed the math_parity one this campaign), REV-016 (recursion-budget global state), REV-017/018/019 (LOW, from 0.0.13 review). BUGFIX-005 (D1-D8 docs) deferred to docs_audit by design.

## 7. Validation Evidence

- Focused suites this review: 98 passed (test_udf_registration_guard, test_filesystem, test_iter4_qa_regression) + 91 passed (evol it1/it6/it7/it10 regression files).
- Master gate (last run, iteration 35, on this exact tree): **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
- All 6 package `__all__` exports resolve (star-import safety re-verified live).
