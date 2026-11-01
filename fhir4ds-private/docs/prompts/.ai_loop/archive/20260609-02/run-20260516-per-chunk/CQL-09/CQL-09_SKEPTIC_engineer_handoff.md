# Engineer Handoff - CQL-09 SKEPTIC

Resolved:
- `QA-CQL09-SKEPTIC-001`: `between` now recursively translates the equivalent
  `>=` and `<=` comparisons. This keeps Quantity and temporal comparison
  dispatch intact instead of comparing translated SQL values directly.
- `QA-CQL09-SKEPTIC-002`: generic equivalence now handles string
  case/whitespace normalization, element-wise list equivalence, tuple
  equivalence by element name, and statically incompatible primitive literals
  before falling back to SQL equality.

Regression coverage added:
- `test_cql_comparison_semantic_edge_cases_match_cpp_and_python` executes
  translated CQL SQL on native-loaded and forced Python fallback DuckDB
  registrations for Quantity `between`, string `~`/`!~`, list `~`, mixed list
  `~`, and tuple `~`.
- Existing list SQL-shape assertion was relaxed from the brittle literal
  substring `NOT CASE` to semantic presence of `NOT` and `CASE`.

Validation:
- `pytest fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py`: 3 passed.
- Adjacent comparison/list/interval/clinical parity slice: 20 passed.
- Official CQL pytest with new comparison regression: 3047 passed, 2 warnings.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
- Full `pytest fhir4ds/ -x --tb=short`: 7161 passed, 5 skipped, 9 warnings.
