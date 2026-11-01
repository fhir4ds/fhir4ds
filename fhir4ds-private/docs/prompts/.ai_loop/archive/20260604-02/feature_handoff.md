# Feature Handoff: CQL Tests Runner FHIR `$cql` Facade

Workflow: feature_implementation
Status: Complete
Plan: `docs/architecture/plans/FEATURE_CQL_TESTS_RUNNER_FACADE.md`

## Implemented

- Added `fhir4ds.cql.fhir_server` with:
  - typed facade config/result metadata/error models;
  - FHIR R4 `Parameters` request parsing and response helpers;
  - synthetic-library expression evaluation through the existing CQL
    translator and DuckDB UDF registration;
  - metadata-driven result serialization for primitives, temporal values,
    Quantity, Ratio, Code, Concept, intervals, lists, tuples, null, empty list,
    empty tuple, and evaluation errors;
  - pure `handle_cql_operation()` API;
  - dependency-free `ThreadingHTTPServer` adapter.
- Added public API exports in `fhir4ds.cql` and top-level `fhir4ds`.
- Added `fhir4ds cql-server` CLI.
- Added `conformance/scripts/run_cql_tests_runner.py` harness with persisted
  raw runner output and summary counts.
- Added developer documentation in `docs/cql-tests-runner-facade.md`.
- Added public translator metadata accessor and tuple/instance type inference
  improvements needed by the facade.
- Added focused unit/integration/API/CLI tests.

## Validation

- Focused facade tests:
  `python3 -m pytest fhir4ds/cql/tests/unit/test_fhir_server_parameters.py fhir4ds/cql/tests/unit/test_fhir_server_serializer.py fhir4ds/cql/tests/unit/test_fhir_server_public_api.py fhir4ds/cql/tests/integration/test_fhir_server_operation.py fhir4ds/cli/tests/test_cql_server_cli.py -q --tb=short`
  -> 16 passed.
- Runner smoke:
  `python3 conformance/scripts/run_cql_tests_runner.py --runner-path /tmp/cql-tests-runner-research --only CqlArithmeticFunctionsTest:Add:Add11 --report conformance/reports/cql_tests_runner_report.json`
  -> pass_count 1, fail_count 0, error_count 0; raw result at
  `conformance/reports/cql_tests_runner_raw/results/202606041256_results.json`.
- Full conformance:
  `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM|SUCCESS|INCOMPLETE"`
  -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  overall 2822/2822, SUCCESS.

## Notes For Review

- The facade intentionally reports open bounded intervals as serializer gaps
  because the current runner `Range`/`Period` extractors infer closed
  boundaries from bound presence and cannot compare open bounds faithfully.
- A broader pre-existing unit subset
  `fhir4ds/cql/tests/unit/test_v2_expressions.py fhir4ds/cql/tests/unit/test_parser.py fhir4ds/cli/tests`
  still has three date-component expectation failures unrelated to this feature
  path. Official conformance remains 100%.
- Scoped `git status`/`git diff --name-only` commands continued to hang in this
  workspace; file-change accounting should use explicit paths or bounded
  commands.
