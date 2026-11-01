# Engineer Handoff - CQL-19 HISTORIAN

## Issues Remediated

- `QA-001`: translated `singleton from` now raises a DuckDB `InvalidInputException` through `error()` for runtime-produced lists with more than one element, while valid singleton extraction still uses `LIST_EXTRACT` to preserve numeric/temporal element type.
- `QA-002`: query-form `take` now routes through the public CQL `Take` macro, matching function-form `Take` semantics for null and non-positive counts.
- `QA-003`: list-returning SQL detection now recognizes `Skip`, `Take`, `Tail`, `jsonConcat`, and CQL list helper outputs, so `Length(...)` over null-list chains returns `0` as required.

## Files Changed

- `fhir4ds/cql/translator/expressions/_lists.py`
- `fhir4ds/cql/translator/expressions/_utils.py`
- `fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py`
- `fhir4ds/cql/tests/unit/test_v2_expressions.py`
- `.temp/qa/cql19_historian_probe.py`
- `extensions/cql/AGENTS.md`

## Validation

- Fresh probe: `python3 .temp/qa/cql19_historian_probe.py` -> passed.
- CQL-19 parity: `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py -q --tb=short` -> 5 passed.
- List/unit cluster: `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py fhir4ds/cql/duckdb/tests/test_list_udfs.py fhir4ds/cql/tests/unit/test_v2_expressions.py -q --tb=short` -> 205 passed.
- Official CQL list category: `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_list_operators -q --tb=short` -> 212 passed.
- Native C++ sqllogictest: `./extensions/cql/build/release/test/unittest '*cql*'` -> 768 assertions passed.
- Full conformance: `python3 conformance/scripts/run_all.py` -> 2822/2822.
- Full pytest: `python3 -m pytest -q --tb=short` -> 7217 passed, 5 skipped, 9 warnings.
- Native/bundled CQL extension SHA-256 matched: `4ba300a57f4b42db9a15e4374c7e40f0932f785dcc92dbd0ad9f463baa9e1f74`.
- Targeted `git diff --check`: clean.
