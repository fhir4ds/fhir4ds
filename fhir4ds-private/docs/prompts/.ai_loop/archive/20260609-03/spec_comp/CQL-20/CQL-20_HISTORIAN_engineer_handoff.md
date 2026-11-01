# Engineer Handoff - CQL-20 HISTORIAN

Resolved `CQL20-HISTORIAN-001`.

Root cause: `_static_list_element_types()` in
`fhir4ds/cql/translator/expressions/_functions.py` returned `None` for several
statically knowable list element expressions. Because aggregate validation is
conservative on unknowns, invalid static aggregate operands fell through to SQL
generation and DuckDB casts/list functions.

Fix:
- Added local classification for nested `ListExpression`, `TupleExpression`,
  `Interval`, `InstanceExpression`, constructor functions, non-null `as`
  assertions, and known conversion/function-return types.
- Preserved conservative behavior for truly dynamic/unknown sources.
- Added regression cases to
  `fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py`.
- Updated `extensions/cql/AGENTS.md` with the aggregate validation boundary.

Files changed:
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql20_historian_probe.py`

Validation:
- Fresh CQL-20 HISTORIAN probe passed.
- Aggregate parity pytest passed: 9/9.
- Official aggregate functions passed: 50/50.
- Full conformance passed: 2822/2822 overall.
