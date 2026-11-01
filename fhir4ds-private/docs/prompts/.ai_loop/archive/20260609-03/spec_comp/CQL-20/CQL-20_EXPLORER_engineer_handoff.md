# Engineer Handoff: CQL-20 EXPLORER

Resolved two HIGH aggregate issues.

`CQL20-EXPLORER-001`: query-form `Product(...)` now lowers to
`system.product` in `_translate_aggregate_pre`, and `_wrap_list_aggregate`
casts `system.product` query columns through `TRY_CAST(... AS DOUBLE)` like the
other numeric row aggregates. This avoids collision with the public CQL
`Product(list)` macro while preserving direct list-function semantics.

`CQL20-EXPLORER-002`: `_static_list_element_types` now infers element types for
simple `Query` nodes by following `QuerySource` list expressions, parenthesized
query wrappers, return aliases represented as `Identifier`, and scalar return
expressions with known static types. `_validate_static_aggregate_argument` now
catches invalid query-produced aggregate sources before SQL generation.

Regression coverage was added to
`fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py` for
query-produced invalid aggregate inputs and query-form `Product` zero/null
behavior. Durable project memory was updated in `extensions/cql/AGENTS.md`.

Validation:

- `python3 .temp/qa/cql20_explorer_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py -q`: 9 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/test_macros_tier1.py::TestAggregateMacros fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q`: 14 passed.
- Official aggregate runner output: aggregate functions 50/50 and aggregate clause 9/9.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`: overall 2822/2822.
