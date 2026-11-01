# QA Handoff — evolution workflow (0.0.15 campaign, duckdb 1.5.5)

## Progress
- Iterations 1-3 Domain 1 (FHIRPath core): it1 SKEPTIC 2 fixes (QA-001/002), it2 HISTORIAN clean, it3 EXPLORER 2 native fixes (QA-003/004).
- Iterations 4-6 Domain 2 (FHIRPath corners): it4 clean, it5 clean, it6 EXPLORER 4 fallback fixes (QA-005..008).
- Iterations 7-9 Domain 3 (CQL translation): QA-009..016 (union dispatch, expand/collapse stored-list, distinct/aggregate over queries, First/Last JSON, native expand render). cql ext REBUILT md5 4e4ff1e3fcbe3cf92157510727cdcf26.
- Iteration 10 Domain 4 (eCQM patterns) SKEPTIC: QA-017 braced-query list selector fixed (3-part, _lists.py + _utils.py). Population attribution probe verified correct across all boundary cases. Gate 2832/2832 after fixing a same-iteration regression (RolledOutIntervals). Regression: test_evol_it10_domain4_skeptic.py (13 tests).
- Iteration 11 Domain 4 HISTORIAN: QA-018 chained-with cross-alias references fixed (nested-EXISTS composition, shared chain scope in _query.py). Multi-group/stratifier/parameter-override walkthrough all correct. Full CQL integration 715 passed. Gate 2832/2832. Regression: test_evol_it11_domain4_historian.py (4 tests).
- Iteration 12 Domain 4 EXPLORER: QA-019 braced-query-as-query-source fixed (AST-narrowed UNNEST branch; first version regressed DQM 3 measures — gate caught it, lesson: AST-narrow query-source shape guards). Domain 4 CLOSED. Gate 2832/2832. Regression: test_evol_it12_domain4_explorer.py.
- Iterations 13-15 Domain 5 (ViewDef): three consecutive CLEAN personalities (SKEPTIC 20+ cases; HISTORIAN 144/144 spec_tests + API surface; EXPLORER deep/wide/exotic fuzz). Domain 5 CLOSED, no code changes.
- Iterations 16-18 Domain 6 (ingestion): three CLEAN personalities, zero code changes (0.0.12/0.0.13 hardening holds on duckdb 1.5.5). Pins: patient_ref stores BARE id; resource:null bundle entries skipped by design; duplicate JSON keys strict-rejected. Domain 6 CLOSED.
- Iterations 19-21 Domain 7 (perf): three CLEAN personalities. Loader/ViewDef/translation scaling linear or better, no leaks, deterministic translation. ENVIRONMENT: duckdb-python 1.5.5 shared-connection cross-thread reads intermittently fail ON VANILLA duckdb (upstream client race; use per-thread connections). Domain 7 CLOSED.
- Iterations 22-24 Domain 8 (error handling): three CLEAN personalities. All public API boundaries raise typed actionable errors; layering verified (loader validates shape, translator validates semantics); adversarial inputs all typed. Domain 8 CLOSED.
- Iterations 25-27 Domain 9 (audit/DQM): QA-020 (audit contains promotion) + QA-021 (audit-full Count comparison multi-row crash, 2 audit-layer defects) fixed; audit causality verified (findings.target names winners). Regression: test_evol_it25_domain9_skeptic.py + test_evol_it27_domain9_explorer.py. Gate 2832/2832 both fixes. Domain 9 CLOSED.
- Iterations 28-30 Domain 10 (install/env): QA-022 fixed (warning named nonexistent fhir4ds.connect() -> create_connection()); site-packages fhirpath ext deployment drift corrected (c7e9b2e3 -> fd81a7c2 repo parity, v1.5.5 cache cleared); installed-copy user simulation clean (native engines, loader, fhirpath). Domain 10 CLOSED.
- Iterations 31-33 Domain 11 (API surface): QA-023 fixed (stale cql __all__ broke star imports — 6 nonexistent names removed); exports/signatures/docs verified; no mutable defaults; attach/viewdef/detach flow verified. Domain 11 CLOSED.
- NEXT: iteration 34 = Domain 12 (medterm4ds) SKEPTIC.

## Issue ledger: 28 (BUGFIX-001..004 RESOLVED, BUGFIX-005 DEFERRED docs_audit, QA-001..017 RESOLVED)

## Binary state
- fhirpath.duckdb_extension md5 fd81a7c2fd30c16dfd7f990624592099 (repo == site-packages)
- cql.duckdb_extension md5 4e4ff1e3fcbe3cf92157510727cdcf26 (repo == site-packages)

## Environment gotchas (cumulative)
- PYTHONPATH=/mnt/d/fhir4ds always (site-packages shadow).
- FileArtifactResolver(include_paths=[<repo>/fhir4ds/cql/resources/cql]) resolves FHIRHelpers for MeasureEvaluator.evaluate.
- MeasureEvaluator needs register_fhirpath(con) + register(con, include_fhirpath=False); load_valuesets takes LIST of ValueSet resources.
- Population SQL final projection orders columns ALPHABETICALLY — map via cursor description.
- `fhirpath_text(res, 'id.value')` returns NULL (id is primitive; no .value child) — probe with bare 'id'.
- Row order of retrieve CTEs is nondeterministic — never order-assert.
- Master gate: cwd=/mnt/d/fhir4ds PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py (~10 min, direct bash timeout 1500000ms).
- Full gate MUST re-run after every fix (it10: RolledOutIntervals; it12: DQM CMS0334/CMS71/CMS832 — both caught by the gate).
- DQM spot-check: PYTHONPATH=/mnt/d/fhir4ds python3 -m fhir4ds.dqm.tests.conformance -m CMS0334,CMS71,CMS832 (~2 min).
- Query-source shape dispatch in _query.py MUST be AST-narrowed — SQL-shape-only guards over-trigger on other lowering paths' shapes.
