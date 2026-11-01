# Code Review Findings: CQL `$cql` Facade

## Scope

Reviewed the implemented CQL test-runner facade and adjacent public surfaces:

- `fhir4ds/cql/fhir_server/`
- `fhir4ds/cli/cql_server.py`
- `conformance/scripts/run_cql_tests_runner.py`
- translator metadata accessor and type-inference changes used by the facade
- focused unit/integration tests for the facade and CLI

## Findings

No open security or implementation findings remain.

Review remediation applied during this pass:

- Added malformed nested `Parameters` input validation so invalid decimal,
  boolean, tuple, period, and CodeableConcept shapes return typed
  `CQLFacadeError` envelopes instead of leaking plain Python exceptions.
- Tightened the oversized HTTP request regression test so an accidental
  non-413 response fails the test.
- Confirmed serializer malformed semantic JSON raises a `serializer-gap`
  facade error rather than a raw JSON decoding exception.
- Confirmed HTTP request size enforcement is configured through
  `CQLServerConfig.max_request_bytes`.

## Security Notes

- No direct SQL interpolation from FHIR request data was found. Runner input
  parameter values are converted into CQL literals, then SQL is produced by the
  existing CQL translator.
- The only direct DuckDB execution in the facade executes translator-generated
  SQL after CQL parsing and translation.
- Broad exception wrapping in the expression service is a user-facing operation
  boundary that converts runtime translator/DuckDB failures into FHIR
  evaluation-error responses; it does not swallow errors silently.

## Verification

- `python3 -m py_compile fhir4ds/cql/fhir_server/types.py fhir4ds/cql/fhir_server/parameters.py fhir4ds/cql/fhir_server/result_serializer.py fhir4ds/cql/fhir_server/expression_service.py fhir4ds/cql/fhir_server/operations.py fhir4ds/cql/fhir_server/app.py fhir4ds/cli/cql_server.py conformance/scripts/run_cql_tests_runner.py`
- `python3 -m pytest fhir4ds/cql/tests/unit/test_fhir_server_parameters.py fhir4ds/cql/tests/unit/test_fhir_server_serializer.py fhir4ds/cql/tests/unit/test_fhir_server_public_api.py fhir4ds/cql/tests/integration/test_fhir_server_operation.py fhir4ds/cli/tests/test_cql_server_cli.py -q --tb=short`

Focused facade validation passed: 19 tests.
