# fhir4ds.cql AGENTS.md

## CQL `$cql` Facade Design Notes

- The planned FHIR `$cql` facade is CQL-specific and belongs under
  `fhir4ds/cql/fhir_server/`; do not create a broad generic FHIR server
  namespace for this V1 conformance harness.
- Keep HTTP/FHIR `Parameters` handling outside the translator. The translator
  may expose immutable result metadata, but it must not know about
  `cqframework/cql-tests-runner` or FHIR operation envelopes.
- Result serialization for the runner must be CQL-metadata-driven. Do not pick
  `valueDate`, `valueTime`, `valueCoding`, `valueRange`, tuple parts, or list
  repetition based only on DuckDB physical type or JSON/VARCHAR transport shape.
- Current runner discovery on 2026-06-04: `$cql` requests post a FHIR
  `Parameters` resource with one `expression` `valueString`; responses are
  extracted from `return` parameters, nested `part`, repeated names, null/empty
  extensions, and `evaluation error` OperationOutcome parameters.
- For V1, keep the HTTP adapter dependency-free unless a later approved design
  adds an optional ASGI/web framework extra. Runner acquisition belongs in a
  conformance script, not as a git submodule.
- Facade parser validation is a public HTTP boundary. Malformed nested
  `Parameters` value shapes must raise typed `CQLFacadeError` results, not
  Python `TypeError`, `KeyError`, `InvalidOperation`, or `JSONDecodeError`
  leaks through `handle_cql_operation()` or the stdlib HTTP adapter.
- Keep the facade request-size cap configurable through
  `CQLServerConfig.max_request_bytes` and covered by HTTP tests. The server is
  a local conformance harness, but it still accepts arbitrary runner request
  bodies.
