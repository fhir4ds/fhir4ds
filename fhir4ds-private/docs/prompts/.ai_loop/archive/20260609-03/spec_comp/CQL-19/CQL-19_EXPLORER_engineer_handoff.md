# Engineer Handoff - CQL-19 EXPLORER

Resolved:
- `QA-001` HIGH. Added a query-row-to-list coercion helper for scalar query-produced lists and routed CQL-19 Part 2 list consumers through it when the CQL AST proves the query source is a scalar list, not a retrieve/resource-backed row source.
- Kept row-shaped retrieve/DQM queries on the existing patient-correlated path after full conformance exposed an over-broad first attempt. The deep-research note is appended in `.ai_loop/state/deep_research_findings.md`.
- `singleton from` over scalar query-produced lists now reaches the list cardinality path, so multi-item scalar lists raise `SingletonFrom` while resource-row subqueries retain current DQM-compatible behavior.

Validation:
- `.temp/qa/cql19_explorer_probe.py`: passed.
- `test_list_part1_parity.py` + `test_list_part2_parity.py`: 17/17 passed.
- Official `CqlListOperatorsTest` subset: 424/424 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Changed implementation/test files:
- `fhir4ds/cql/translator/expressions/_utils.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_temporal_intervals.py`
- `fhir4ds/cql/translator/expressions/_lists.py`
- `fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql19_explorer_probe.py`
