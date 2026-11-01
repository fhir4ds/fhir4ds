# Architect Handoff — SOF-SQ-03 (iteration 1)

## Golden Standard (chunk-scoped invariants, verified)
1. `fhir4ds/viewdef/` must never import `fhir4ds/sqlquery/` — VERIFIED (grep: zero import statements; docstring mentions only).
2. Every sqlquery error ⊂ `SQLError` ⊂ `SQLOnFHIRError` ⊂ `ValueError` — VERIFIED (MRO check, all 7 error classes).
3. Every dependency-materialization failure surfaces as `SQLQueryMaterializationError` with label+canonical context — VERIFIED post-fix (all post-resolver paths wrapped; cycles re-raise as `SQLQueryCycleError`).
4. Resolver returns of every documented shape (dict VD, dict Library, parsed VD/SQLQuery/SQLView) are handled via structural/isinstance detection; ambiguous shapes fail typed — VERIFIED post-fix.
5. Identifiers (labels, parameter names) obey sql-name — VERIFIED post-fix.
6. No resource-specific hardcoding in runner/validator — VERIFIED (registry-driven coercion, no resource-type branches).

## Audit of the iteration's changes
`_resolve_view_sql` extraction preserves the one-way dependency (imports viewdef lazily as before), keeps cycle semantics, and adds no silent fallbacks. Broad `except Exception` wrapping is bounded with explicit re-raises for `SQLQueryCycleError`/nested `SQLQueryMaterializationError` — correct carve-outs. No architectural drift entries.

## QA Enforcer Gate
QA (SKEPTIC) tested every mandated config.notes item end-to-end on a real DuckDB connection (chains, cycle, all ambiguous shapes, transitivity, grep-verified one-way dependency, full API export audit) and produced 4 real findings, including one untyped duckdb exception leak. Sufficient. **RETRY_QA: false.**

## State
4/4 issues RESOLVED and re-verified (sqlquery 109/109, viewdef 1241/1241 unit; master gate 2832/2832). Tombstoned in `evolution.json`; details archived to `ARCHIVE_LOG.md`. Zero non-terminal issues → clean exit eligible (iteration 1 ≥ min_iterations 1).

## Recommended Fix Order
None — no open work for the engineer.
