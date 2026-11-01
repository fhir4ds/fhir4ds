# Engineer Handoff - CQL-08 SKEPTIC

Resolved both QA findings for CQL nullological `Coalesce` semantics.

## Fixed

- `QA-001` HIGH: translated `Coalesce(List<T>)` now accepts query-produced lists, including query-list definition aliases. The translator lowers those query lists to a scalar subquery that selects the first non-null value.
- `QA-002` MEDIUM: public direct DuckDB `Coalesce` now rejects invalid scalar arities outside the CQL-defined 2 through 5 scalar overloads, while preserving the valid single-list overload.

## Validation

- `python3 .temp/qa/cql08_skeptic_probe.py`: passed
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py -q`: 8 passed
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py -q -k CqlNullologicalOperatorsTest`: 44 passed
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py -q`: 39 passed
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822

## Changed Files

- `fhir4ds/cql/duckdb/udf/logical.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py`
- `.temp/qa/cql08_skeptic_probe.py`
- `extensions/cql/AGENTS.md`
