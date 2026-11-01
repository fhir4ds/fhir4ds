# Engineer Handoff — SOF-SQ-03 (iteration 1)

All four issues RESOLVED; none DEFERRED/NEEDS_CONTEXT.

## Fixes
1. **SOF-SQ-03-QA-001 (HIGH)** — `fhir4ds/sqlquery/runner.py`: extracted dependency shape handling into `_resolve_view_sql`, which now accepts parsed `SQLQuery`/`SQLView` objects via isinstance (recursively materializing their deps, then using their best-supported SQL body), matching the documented `DependencyResolver` contract and spec canonical(ViewDefinition or SQLView).
2. **SOF-SQ-03-QA-002 (HIGH)** — runner: the entire post-resolver path (shape detection, parse, dialect selection, SQL generation, `quote_identifier`, `CREATE OR REPLACE VIEW`) is wrapped into `SQLQueryMaterializationError` carrying `label` + `resource` context. `SQLQueryCycleError` and nested `SQLQueryMaterializationError` re-raise untouched so cycle semantics and inner context survive.
3. **SOF-SQ-03-QA-003 (MEDIUM)** — runner `_resolve_view_sql`: dict carrying `resourceType='Library'` *and* ViewDefinition structure (`select`+`resource`) raises a typed ambiguous `SQLQueryMaterializationError` instead of misrouting to the viewdef parser.
4. **SOF-SQ-03-QA-004 (MEDIUM)** — `fhir4ds/sqlquery/validator.py`: `parameter.name` must satisfy `SQL_NAME_PATTERN` (sql-name) — same guard as labels; enforced via shared `validate_sql_library(strict=True)` so parser and dataclass paths both hit it.

## Regression tests
`fhir4ds/sqlquery/tests/test_integration.py::TestSofSq03IntegrationSeams` (7 tests): parsed SQLView-object dep, parsed SQLQuery-object dep, inner parse-failure wrapping with context, CREATE VIEW failure wrapping, ambiguous dict rejection, cycle through parsed objects still `SQLQueryCycleError`, parameter sql-name rejection.

## Validation
- sqlquery unit suite: 109/109 (was 102).
- Master gate (final tree, PYTHONPATH=/mnt/d/fhir4ds): ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832 — baseline held, no regressions.

No new issues discovered during remediation. Workflow is `evolution`; advancing to ARCHITECT.
