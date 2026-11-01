# Engineer Handoff: CQL-09 EXPLORER

Resolved issues:
- `QA-001` HIGH: Tuple equality now delegates element comparison back through semantic CQL comparison lowering. Quantity tuple fields use `quantity_compare`, Ratio tuple fields use `ratioCompare`, and incompatible Quantity dimensions propagate `NULL`.
- `QA-002` HIGH: Static tuple fields from list/query aliases and `singleton from` preserve Quantity/Ratio type evidence without storing CQL parser ASTs in `SymbolInfo.ast_expr`. Tuple-list aliases now read the tuple JSON value directly instead of `alias.resource`.

Changed source/tests:
- `fhir4ds/cql/translator/context.py`
- `fhir4ds/cql/translator/expressions/_query.py`
- `fhir4ds/cql/translator/expressions/_property.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql09_explorer_probe.py`

Validation:
- `.temp/qa/cql09_explorer_probe.py`: PASS on forced Python fallback and native-loaded registration.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py -q`: 9 passed.
- `python3 conformance/scripts/run_cql.py`: 1706/1706, including `CqlComparisonOperatorsTest.xml: 198/198`.
- `python3 conformance/scripts/run_dqm.py`: 47/47, including `CMS190: PASSED`.
- `python3 conformance/scripts/run_all.py`: 2822/2822 overall.

Recovery note: The first metadata fix stored parser ASTs in `SymbolInfo.ast_expr` and caused CMS190 to fail with `BinaryExpression` lacking `to_sql`. The final fix uses dedicated `_alias_source_asts` metadata so type inference cannot leak parser nodes into SQL generation.
