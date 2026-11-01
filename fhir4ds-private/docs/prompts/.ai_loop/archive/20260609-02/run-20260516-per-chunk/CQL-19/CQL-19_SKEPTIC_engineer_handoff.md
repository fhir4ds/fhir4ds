# Engineer Handoff: CQL-19 SKEPTIC

## Scope

Remediated CQL List Operators Part 2 parity findings from QA: `Skip`,
list `properly includes`, list `properly included in`, list `union`, and
direct public `SingletonFrom`.

## Changes

- `fhir4ds/cql/duckdb/macros/list.py`
  - Updated `Skip(lst, n)` so null count returns the original list and negative
    count returns an empty list.
  - Hardened `CQLListContainsEq` and `CQLListHasAllEq` against untyped
    `NULL` binder errors by unnesting `COALESCE(..., [])` in helper subqueries.
- `fhir4ds/cql/translator/expressions/_lists.py`
  - Routed query-form skip through the public `Skip` macro instead of raw
    `LIST_SLICE`, preserving null/negative count semantics.
- `fhir4ds/cql/translator/expressions/_operators.py`
  - Routed list `properly includes` / `properly included in` through
    `CQLListContainsEq` / `CQLListHasAllEq` so Quantity equality and null
    element semantics match CQL.
  - Added null-container short-circuiting for official proper-inclusion null
    cases.
  - Changed list `union` null/null lowering to return an empty list rather than
    SQL NULL.
- `extensions/cql/src/cql_extension.cpp`
  - Changed no-Python/browser-style C++ `SingletonFrom` to raise
    `InvalidInputException` for multi-item lists.
- Tests updated in list parity, list UDF, SQL logic, and translator unit suites.
  The fresh probe `.temp/qa/cql19_skeptic_probe.py` now covers the remediated
  edge cases across forced Python fallback, native-loaded registration, and
  no-Python/browser-style C++.

## Validation

- `python3 .temp/qa/cql19_skeptic_probe.py`: PASS.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py fhir4ds/cql/duckdb/tests/test_list_udfs.py -q --tb=short`: 57 passed.
- `./extensions/cql/build/release/test/unittest "*cql*"`: all tests passed, 768 assertions.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q --tb=short`: 5 passed.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_list_operators -q --tb=short`: 212 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM|SUCCESS|Passed|Overall"`:
  2822/2822 overall, CQL 1706/1706.
- `python3 -m pytest -q --tb=short`: 7216 passed, 5 skipped, 9 warnings.
- Targeted `git diff --check`: PASS.

## Notes For Architect

The first post-remediation conformance pass exposed two official null-container
proper-inclusion cases that were not in the initial QA issue list:
`null properly includes {2}` and `{'s','u','n'} properly included in null`.
Those were fixed in the translator and added to the fresh probe and parity test.
