# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Design and implement a minimal FHIR server facade that lets FHIR4DS run the
official `cqframework/cql-tests-runner` suite against the local CQL engine.

The facade should expose the FHIR `$cql` operation expected by
`https://github.com/cqframework/cql-tests-runner`, evaluate incoming CQL using
FHIR4DS, and return results as FHIR `Parameters` resources in the typed shape
the runner expects for CQL comparison.

Primary outcome: a local conformance harness where `cql-tests-runner` can call
FHIR4DS through a FHIR-compatible `$cql` HTTP endpoint, with type-correct CQL
result serialization for primitive, temporal, clinical, quantity, interval,
list, and tuple values.

## Pipeline
1. feature_design
2. feature_implementation
3. code_review
4. pre_release
5. docs_audit

## Feature Plan

No pre-approved implementation plan exists yet. Start with `feature_design` and
produce a refined design for user approval before implementation.

The feature design must decide the final API/module placement, dependency
strategy, request/response contract, type-metadata strategy, and runner
integration approach before any code is written.

### External Reference Points

- Target runner: `https://github.com/cqframework/cql-tests-runner`
  - As of the 2026-06-04 discussion, the runner README says it runs tests
    against a server of choice using the FHIR `$cql` operation.
  - The current runner state says it uses only `$cql`; it does not currently
    expect other FHIR server capabilities.
  - The current CQL tests repository used by the runner says tests have no data
    access expectations and no retrieve expressions.
  - The runner expects engine output as a FHIR `Parameters` resource and
    converts typed FHIR values back into a JavaScript CQL comparison shape.
- Important runner extraction behavior observed from current source:
  - `valueDate` is extracted as a CQL Date literal string prefixed with `@`.
  - `valueDateTime` is extracted as a CQL DateTime literal string prefixed with
    `@`, with a trailing `T` for date-only DateTime precision.
  - `valueTime` is extracted as a CQL Time literal string prefixed with `@T`.
  - `valueInteger`, `valueDecimal`, `valueBoolean`, and `valueString` are
    extracted directly.
  - `valueQuantity` is extracted to `{ value, unit }`, using Quantity `code` as
    the unit when present.
  - `valueRatio` is extracted into numerator/denominator Quantity shapes.
  - `valueCoding` is extracted as CQL Code shape.
  - `valueCodeableConcept` is extracted as CQL Concept shape.
  - `valueRange` and `valuePeriod` are extracted as interval-like values.
  - The runner README calls out intervals as FHIR `Range` plus `cqf-cqlType`.
  - Null, empty list, and empty tuple are represented through FHIR extensions
    such as `data-absent-reason`, `cqf-isEmptyList`, and `cqf-isEmptyTuple`.
- FHIR operation reference:
  - FHIR `$cql` operation: `https://hl7.org/fhir/OperationDefinition-cql.html`
  - FHIR `Parameters` resource: `https://hl7.org/fhir/parameters.html`

### Scope

1. Add a narrow CQL/FHIR facade, not a general-purpose FHIR persistence server.
   The initial server surface should be limited to the FHIR `$cql` operation
   and minimal health/metadata endpoints only if required by tooling.
2. Tentative module placement for design review:
   - `fhir4ds/cql/fhir_server/`
   - Possible files:
     - `app.py` for an ASGI/FastAPI or similarly lightweight HTTP app.
     - `operations.py` for `$cql` operation handling.
     - `parameters.py` for FHIR `Parameters` parsing/building.
     - `result_serializer.py` for CQL result to FHIR `Parameters` conversion.
     - `types.py` for CQL result metadata models.
3. The design must confirm whether this belongs under `fhir4ds.cql`, a new
   `fhir4ds.server` namespace, or a test/conformance-only package surface.
4. The initial facade should support pure-expression CQL tests from
   `cql-tests-runner`. Data retrieve support is out of scope for V1 unless the
   feature design proves the runner now requires it.
5. Do not build a FHIR resource store, FHIR search API, terminology server, or
   Library/$evaluate implementation in V1 unless the design proves it is
   necessary for the current runner contract.
6. The facade must accept runner-compatible `$cql` requests, extract the CQL
   expression/library payload and parameters, evaluate through the existing
   FHIR4DS CQL engine, and return FHIR `Parameters`.
7. Serialization must be type-aware. Do not infer CQL type only from a DuckDB
   physical type or JSON/VARCHAR transport shape.
8. Add or expose explicit CQL result metadata where needed:
   - CQL type name, such as `System.Date`, `System.DateTime`,
     `System.Quantity`, `System.Code`, `System.Concept`, `Interval<T>`,
     `List<T>`, or `Tuple`.
   - Temporal precision and timezone/offset text where relevant.
   - Decimal precision where relevant and available.
   - Interval point type and open/closed boundary metadata.
   - List element type and tuple element names/types.
9. Prefer metadata plumbing over translator semantic rewrites. Translator
   changes should be limited to preserving/exposing result type metadata unless
   a real evaluator bug is discovered.
10. Support a typed serializer mapping at minimum:
    - Boolean -> `valueBoolean`
    - Integer -> `valueInteger`
    - Long -> design-required decision, because FHIR R4 primitive support and
      runner extraction may need an extension-backed or compatible fallback.
    - Decimal -> `valueDecimal`
    - String -> `valueString`
    - Date -> `valueDate`
    - DateTime -> `valueDateTime`
    - Time -> `valueTime`
    - Quantity -> `valueQuantity`
    - Ratio -> `valueRatio`
    - Code -> `valueCoding`
    - Concept -> `valueCodeableConcept`
    - Interval<Date/DateTime/Time> -> design-required mapping, likely
      `valuePeriod` or extension-backed representation where FHIR cannot carry
      full CQL precision.
    - Interval<Quantity> -> `valueRange` plus CQL type metadata.
    - List<T> -> repeated/nested FHIR `Parameters.parameter` entries that the
      runner extracts as CQL lists.
    - Tuple -> nested FHIR `Parameters.part` entries.
    - Null/empty list/empty tuple -> runner-compatible extensions.
11. Runner integration should initially be an optional conformance harness, not
    a hard package runtime dependency.
12. Do not add `cqframework/cql-tests-runner` as a Git submodule unless the
    feature design explicitly justifies it. Prefer one of:
    - published Docker image, pinned by tag or digest;
    - user-supplied `CQL_TESTS_RUNNER_PATH`;
    - scripted clone/download of a pinned commit into `.temp` or a CI cache.
13. Add a conformance script, tentatively:
    - `conformance/scripts/run_cql_tests_runner.py`
    - output: `conformance/reports/cql_tests_runner_report.json`
14. The script should support quick/only-list execution first, then full suite
    expansion as serializer coverage matures.

### Design Questions To Answer Before Implementation

1. What exact `$cql` request shape does the current runner send?
2. Which FHIR version should the facade target for `Parameters` serialization
   in V1, and how does that interact with CQL Long, DateTime precision, Time,
   and intervals?
3. What existing FHIR4DS CQL API should execute raw runner CQL: direct
   translator, measure evaluator, DuckDB UDF path, or a new narrow service
   adapter?
4. Where is result type metadata currently preserved, where is it erased, and
   what is the smallest metadata model needed for the facade?
5. Can pure-expression runner tests be evaluated without a FHIR data model or
   source adapter? If yes, keep V1 independent of `FHIRDataLoader`.
6. How should evaluation errors be serialized? The runner has an
   `evaluation error` extraction path using an embedded `OperationOutcome`.
7. How should skipped/unsupported runner cases be reported so gaps are visible
   and not hidden as environment skips?
8. Which runner tests should make up the first acceptance slice?
9. What optional dependencies are acceptable for serving HTTP: FastAPI,
   Starlette, Flask, stdlib HTTP, or an existing project dependency?
10. Should the server be exposed as a CLI command, a Python function returning
    an ASGI app, or both?

### Implementation Constraints

- Follow existing `fhir4ds.cql` translator invariants and AGENTS guidance.
- Keep CQL semantic behavior unchanged unless a real bug is found.
- Do not rely on DuckDB physical result types alone to choose FHIR output
  primitives; typed metadata must drive serialization.
- Preserve primitive distinction between String and Date/DateTime/Time even
  when runtime transport is `VARCHAR`.
- Preserve clinical distinction between Code, Concept, ValueSet, and CodeSystem
  where those values can appear in runner tests.
- Preserve Quantity and Ratio JSON shape and unit/code semantics.
- Preserve interval point type and boundary closure semantics.
- Strictly separate invalid CQL translation/evaluation errors from normal CQL
  null results.
- Avoid leaking request bodies, credentials, or full CQL payloads in exception
  logs unless a debug flag is explicitly enabled.
- If package metadata, optional dependencies, CLI commands, docs navigation, or
  release artifacts change, final validation must include the release/artifact
  gate after implementation.

### Documentation Deliverables

- Developer documentation for the `$cql` facade and why it is intentionally
  narrower than a full FHIR server.
- A conformance runner guide showing how to run `cqframework/cql-tests-runner`
  against FHIR4DS locally.
- A compatibility matrix for supported CQL result types and any known
  runner/FHIR serialization limitations.
- If public API or CLI commands are added, update the relevant package docs and
  website navigation.

### Verification Expectations

- Unit tests for FHIR `Parameters` result serialization:
  - primitive scalar types;
  - Date, DateTime, and Time literal marker compatibility;
  - Quantity and Ratio;
  - Code and Concept;
  - intervals;
  - lists and tuples;
  - null, empty list, and empty tuple;
  - evaluation errors.
- Unit tests for `$cql` request parsing and invalid-request errors.
- Integration tests for the facade evaluating a small set of raw CQL
  expressions end to end.
- Runner smoke tests using `cql-tests-runner` `OnlyList` or equivalent quick
  execution against the local facade.
- Full runner execution should be attempted once the serializer supports enough
  types; unsupported cases must be reported explicitly.
- Existing CQL translator, DuckDB registration, and conformance suites must
  remain green after implementation.

## Focus Areas

- Start with design. Do not implement until the refined feature design has been
  produced and approved.
- Keep V1 narrow: FHIR `$cql` facade for CQL spec tests, not a full FHIR
  server.
- Treat typed CQL result serialization as the core feature.
- Metadata preservation is the main architectural risk. Identify and close
  metadata erasure boundaries before broadening test coverage.
- Avoid adding `cql-tests-runner` as a submodule unless there is a strong,
  documented reason.
- Prefer an optional conformance harness that can run in CI or locally without
  making Node/Docker mandatory for normal package users.
- Make failures actionable: distinguish unsupported runner feature, translation
  error, evaluation error, serializer gap, and runner infrastructure failure.
