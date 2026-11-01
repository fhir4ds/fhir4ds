# Architecture Self-Audit: CQL Tests Runner FHIR `$cql` Facade

Status: Completed for draft v1

## Golden Invariants

1. HTTP/FHIR request handling must stay outside the CQL translator. The
   translator remains a CQL-to-SQL compiler, not a FHIR server.
2. Result serialization must be driven by CQL semantic metadata, not by DuckDB
   physical types or JSON/VARCHAR transport shape.
3. The facade must fail explicitly for unsupported `$cql` inputs such as data,
   external content endpoints, or retrieve-dependent expressions; it must not
   silently ignore them.
4. Runner compatibility must be verified against actual runner extractor shapes,
   not assumed from generic FHIR type names.
5. The local HTTP adapter must not introduce mandatory runtime dependencies for
   normal package users.
6. Error responses must distinguish invalid request, unsupported feature,
   parse/translation error, runtime evaluation error, and serializer gap.
7. The conformance harness must not add `cqframework/cql-tests-runner` as a git
   submodule unless a later plan justifies it.
8. Any public API, CLI, optional dependency, or artifact change must go through
   pre-release artifact validation.

## Findings

### Finding 1: Input parameter support was underspecified

Draft v1 said the request parser should handle nested input `parameters`, but
did not state how they become available to the synthetic CQL expression. This
would violate invariant 3 because the service might parse values and then fail
later through unclear identifier errors.

Refinement: final plan must define static CQL parameter declaration generation
from FHIR input parameter metadata, with explicit unsupported errors for shapes
that cannot be represented safely.

### Finding 2: Tuple/list metadata is a known local gap

Local probes show tuple selectors infer as `Any`, and lists of tuples infer as
`List<Any>`. A serializer that guesses from runtime JSON would violate
invariant 2.

Refinement: final plan must make tuple/list/interval metadata preservation a
first-class implementation task before broad serializer acceptance.

### Finding 3: Long serialization needs a conservative V1 decision

FHIR R4 `Parameters.value[x]` has `valueInteger` and `valueDecimal` but no
native Long primitive. The runner extractor currently has integer and decimal
extractors, not a dedicated Long extractor.

Refinement: final plan should serialize Long as `valueDecimal` with
`cqf-cqlType: System.Long` for V1 and add a runner smoke case; if that does not
compare correctly, Long is reported as an explicit serializer gap.

### Finding 4: Dependency-free HTTP is architecturally safer for V1

Adding FastAPI just for one local endpoint would change package dependency and
artifact behavior before the facade proves value. A stdlib adapter is enough
for the runner's POST-only contract.

Refinement: final plan should keep core operations dependency-free and use
`ThreadingHTTPServer` for V1. Future ASGI support can be optional.

### Finding 5: OperationOutcome placement must match runner extraction

FHIR operations often return an `OperationOutcome` directly for HTTP-level
failures, but the runner has a special `$cql` result extraction path for a
`Parameters` resource containing parameter name `evaluation error`.

Refinement: final plan must use HTTP 400/422 with direct `OperationOutcome` for
invalid request envelopes, and HTTP 200 `Parameters` with `evaluation error`
for CQL evaluation/translation failures that correspond to a test result.

## Audit Result

Draft v1 is structurally sound after refinement, provided the final FDD makes
metadata preservation and unsupported-feature reporting explicit acceptance
criteria.
