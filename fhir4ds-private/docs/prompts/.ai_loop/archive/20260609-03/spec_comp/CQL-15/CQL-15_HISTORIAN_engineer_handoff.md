# Engineer Handoff: CQL-15 HISTORIAN

## Issue Resolved

`QA-001` HIGH, SPEC_VIOLATION.

Root cause:
- Python and no-Python C++ `intervalContains` inherited generic SQL null
  propagation for a null interval/container argument.
- Translated CQL did not detect definitely-null interval/list containers in
  `contains` and `in`, so it fell through to DuckDB `system.contains` or SQL
  `IN`, both of which return SQL NULL for null containers.
- Untyped `Interval[null, null]` was not treated as a null interval for
  `contains`.

Fixes:
- `fhir4ds/cql/duckdb/udf/interval.py`: `intervalContains` and
  `intervalContainsPrecise` now return false for null container/interval
  arguments and keep null point/precision behavior as SQL NULL.
- `extensions/cql/src/cql_extension.cpp`: no-Python C++ `intervalContains`
  and `intervalContainsPrecise` now implement the same null-container rule.
- `fhir4ds/cql/translator/expressions/_operators.py`: added definitely-null
  AST/SQL detection for interval/list containment; `in` over definitely-null
  interval/list arguments lowers to false; untyped `Interval[null, null]
  contains point` lowers to false.
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py`: added
  forced Python/native/no-Python parity coverage for null-container contains/in
  behavior.
- Rebuilt and copied `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.

## Validation

Passed:
- `python3 .temp/qa/cql15_historian_probe.py`
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q` — 26 passed
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_interval_operators -q` — 412 passed
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` — 2822/2822 overall

## Residual Risk

No known open issue from this pass. The public direct helper cannot infer a
typed point domain for all-null JSON interval bounds; translated CQL handles
untyped `Interval[null, null]` explicitly before calling helpers.
