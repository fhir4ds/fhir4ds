# Engineer Handoff — CQL-20 EXPLORER

## Remediation Summary

Resolved both QA issues from the fresh EXPLORER probe.

- `QA-001`: query-shaped `Min`/`Max` over Date, Time, and String lists no
  longer cast their values to `DOUBLE`. The aggregate wrapper now reserves
  `TRY_CAST(... AS DOUBLE)` for numeric-only aggregate functions.
- `QA-002`: direct public `Median(list)`, `Mode(list)`, `StdDev(list)`,
  `Variance(list)`, `PopulationStdDev(list)`, and `PopulationVariance(list)`
  now use CQL list semantics. Query-form translated statistical aggregates
  call DuckDB `system.*` row aggregates explicitly to avoid colliding with the
  direct CQL list macro names.

## Files Changed

- `fhir4ds/cql/duckdb/macros/__init__.py`
- `fhir4ds/cql/duckdb/macros/aggregate.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py`
- `fhir4ds/cql/duckdb/tests/test_macros_tier1.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql20_explorer_probe.py`

## Validation

- Fresh probe: `python3 .temp/qa/cql20_explorer_probe.py`
- Focused aggregate/macro tests: `72 passed`
- Full CQL pytest: `4986 passed, 5 skipped, 6 warnings`
- Unified conformance: `2822/2822`, 100%
- Full repo pytest: `7221 passed, 5 skipped, 9 warnings`
- Targeted `git diff --check`: clean

## State

`evolution.json` is advanced to `phase: "ARCHITECT"` with `QA-001` and
`QA-002` marked `RESOLVED`.
