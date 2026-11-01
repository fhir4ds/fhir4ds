# QA Handoff — SOF-VD-11 HISTORIAN (2026-08-23, iteration 1)

Personality: HISTORIAN. Chunk: View Runner + Examples (parser validation, SQL
generation, DuckDB execution, official spec fixtures). Mandate: re-verify the
SKEPTIC's fix is spec-correct and regression-free, but hunt NEW divergences.

## Probes (all in /mnt/d/fhir4ds/.temp/qa/sof_vd11_historian/)

probe1.py — runner surfaces:
- P1 PASS: MULTI-resource shared `resources` table (Patient+Observation+Specimen+noise): resourceType filtering through SQLGenerator(source_table="resources") correct under native AND forced Python fallback; no cross-type rows.
- P2 PASS: materialization via CREATE OR REPLACE VIEW — catalog column types exactly {key VARCHAR, bd VARCHAR (date doctrine), gender VARCHAR}; same VD executed twice (view overwrite) stable; 3 different VDs (Patient flat, forEach address, Observation nested forEach) in one session, no state pollution.
- P3 PASS: empty input table → 0 rows out, catalog types still declared correctly, native==fallback.
- P4 PASS: temporal column types identical native==fallback for scalar date AND collection date (VARCHAR / VARCHAR[]).
- P5 PASS: runner error paths typed — missing `select` → ParseError/ValidationError at parse; cross-resource element-ID type → ValidationError/GenerationError at generation (never deferred to execute); missing source table → duckdb CatalogError at execute.
- P6 PASS: public runner surface `fhir4ds.generate_view_sql` (str/dict/ViewDefinition inputs, TypeError on int, default shared-table filter, source_table=None → pluralized `patients` table SQL, end-to-end execution).

probe2_ig_multi.py — all five published IG 2.0.0 Binary examples executed
against a MULTI-resource shared table including Specimen and non-BP
Observation noise: 2/3/1/1/1 rows, native==fallback row-for-row, zero
cross-type leakage. (Initial 0-row UsCoreBloodPressures was a fixture error:
components lacking coding.system → empty forEach → Cartesian row suppression,
per pinned Process(S,N) doctrine — NOT a bug.)

## Spec snapshot drift
spec_tests 22/22 md5-identical to FHIR/sql-on-fhir.js HEAD
7969489777b72ea87e866c320c461f7a13df9388 (2026-07-15) — NO DRIFT.
Note: /mnt/d/sql-on-fhir-v2 is a stale (2024-02) personal fork clone — its
/tests are the known STALE DRAFT fixtures; do not use for drift checks.

## API-doc vs export audit
fhir4ds/viewdef/__init__.py `__all__` exactly matches imports (no doc/export
divergence); fhir4ds top-level lazily exposes generate_view_sql /
parse_view_definition consistently with docstrings.

## Findings
Zero CRITICAL/HIGH/MEDIUM issues. Zero issues logged. SKEPTIC QA-001 fix
(no dead unsigned-retry in fhirpath/duckdb/extension.py) verified present
and behavior correct via native/fallback paired probes.

## Gates (fresh, final tree)
ViewDef conformance 144/144; master run_all.py 2832/2832; fhirpath binary
md5 57d0634b6ee6eddee9fc06a1355bef5a, cql c5b22d58310c1eb7bafa17ce7877f989 —
repo == site-packages (no rebuild; no code changes this launch).
