# QA Handoff — SOF-SQ-03 (iteration 1, SKEPTIC)

## Scope
Cross-package integration, error model integration, public API surface of `fhir4ds/sqlquery` per `config.notes`.

## Verified PASS (no issue)
- One-level chain (SQLQuery → ViewDefinition dict): correct rows via real DuckDB + Python-fallback fhirpath UDFs (`[('female',1),('male',1)]`).
- Two-level chain (SQLQuery → SQLView → ViewDefinition): recursive materialization correct (`[('male',)]`).
- Cycle: SQLView A→B→A raises `SQLQueryCycleError` before execution.
- Error transitivity: every sqlquery error ⊂ `SQLError` ⊂ `SQLOnFHIRError` ⊂ `ValueError`; viewdef `ParseError` also inside hierarchy.
- One-way dependency: `fhir4ds/viewdef/` never imports `fhir4ds/sqlquery/` (docstring mentions only).
- Public API: all mandated names exported with docstrings (`parse_library`, `parse_sqlquery`, `parse_sqlview`, `validate_sql_library`, `select_best_content`, `SQLQueryRunner`, `DependencyResolver`).
- Parsed `ViewDefinition` objects via isinstance: handled.
- Resolver returning a string: wrapped as `SQLQueryMaterializationError`.

## Issues (all OPEN)
- **SOF-SQ-03-QA-001 (HIGH)**: resolver returning parsed `SQLQuery`/`SQLView` object rejected ("unsupported type SQLView") — documented DependencyResolver contract + spec canonical(ViewDefinition or SQLView) say these are valid targets.
- **SOF-SQ-03-QA-002 (HIGH)**: raw exception leaks inside `_materialize_one` — duckdb Catalog/Binder exceptions from `CREATE OR REPLACE VIEW` escape untyped (not even `SQLOnFHIRError`); inner parse errors not wrapped with label/canonical context.
- **SOF-SQ-03-QA-003 (MEDIUM)**: ambiguous dict (`resourceType='Library'` + profile + `select`/`resource` keys) misrouted to viewdef parser, dying with a viewdef `ParseError` instead of a typed sqlquery error.
- **SOF-SQ-03-QA-004 (MEDIUM)**: `parameter.name` not validated against sql-name (labels are; parameters aren't), contradicting the package docstring and models.fsh invariant.

Repro scripts: `/mnt/d/fhir4ds/.temp/qa/explore2.py`, `explore3.py`.

Advancing to FIX per MASTER_ORCHESTRATOR.
