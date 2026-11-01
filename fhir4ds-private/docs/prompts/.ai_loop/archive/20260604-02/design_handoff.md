# Design Handoff: CQL Tests Runner FHIR `$cql` Facade

Workflow: feature_design
Status: Waiting for user approval
Final plan: `docs/architecture/plans/FEATURE_CQL_TESTS_RUNNER_FACADE.md`

## Summary

The refined design keeps the feature under `fhir4ds.cql` as a narrow
`fhir_server` facade. It adds a dependency-free `$cql` HTTP adapter for local
runner use, a pure operation handler, request/response `Parameters` utilities,
an expression evaluation service, and a metadata-driven result serializer.

The key architectural decision is that serializer behavior must be driven by CQL
semantic metadata, not by DuckDB physical values. Local discovery found that the
translator already exposes useful `DefinitionMeta`, but tuple and some
list/interval metadata gaps must be closed before broad runner coverage.

## Refinements From Self-Audit

- Added explicit static CQL parameter declaration strategy for nested input
  `parameters`, with categorized unsupported errors.
- Made tuple/list/interval metadata preservation an implementation task and
  acceptance criterion.
- Chose stdlib `ThreadingHTTPServer` for V1 to avoid mandatory web framework
  dependencies.
- Split error handling into invalid-request direct `OperationOutcome` versus
  runner-compatible `evaluation error` Parameters responses.
- Recorded Long as a conservative V1 serializer decision: `valueDecimal` plus
  `cqf-cqlType: System.Long`, with explicit gap reporting if runner comparison
  disagrees.

## Approval Gate

Implementation must not start until the human approves the final feature plan
with `APPROVED` or `EXECUTE` in chat or `USER_DIRECTIVES.md`.
