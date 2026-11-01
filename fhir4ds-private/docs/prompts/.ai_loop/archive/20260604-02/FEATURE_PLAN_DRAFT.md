# Feature Plan Draft: CQL Tests Runner FHIR `$cql` Facade

Status: Draft v1 for architecture self-audit
Target package version: 0.0.7

## Objective

Design and implement a narrow FHIR R4-compatible `$cql` facade that lets
`cqframework/cql-tests-runner` evaluate official CQL test expressions against
the local FHIR4DS CQL engine.

The facade is not a general FHIR server. It accepts runner-compatible
`Parameters` requests, evaluates the `expression` parameter through FHIR4DS CQL,
and returns a `Parameters` response whose `return` parameter uses runner-readable
FHIR `value[x]`, `part`, and extension shapes.

## Spec Alignment

External references verified during design:

- HL7 Using CQL With FHIR `$cql`: the operation evaluates one CQL expression at
  `[base]/$cql`, takes a required `expression` string, optional nested
  `parameters`, and returns one or more `return` parameters in a FHIR
  `Parameters` resource.
- FHIR R4 Operations: operation POST bodies and responses are `Parameters`
  resources, and operation parameters may be data types, resources, or parts.
- FHIR R4 `Parameters`: every parameter has a required `name` and exactly one of
  `value[x]`, `resource`, or `part`.
- FHIR R4 `OperationOutcome`: use it for parser, translation, evaluation,
  unsupported-feature, and serializer errors.
- CQL tests page: the official tests are informative consistency tests; the CQL
  spec remains source of truth.
- Current `cqframework/cql-tests-runner` README/source:
  - current runner uses only `$cql`;
  - current tests have no retrieve/data-access expectations;
  - request body for `$cql` is `Parameters.parameter[{name:"expression",
    valueString:<raw expression>}]`;
  - result extraction expects `return` parameters, nested tuple/list `part`
    entries, null/empty extensions, and evaluation errors under parameter name
    `evaluation error`.

## Local Discovery

- `fhir4ds.cql.parse_cql()` parses full CQL libraries.
- `CQLToSQLTranslator.translate_library_to_sql()` can evaluate a one-definition
  scalar library without a resources table for simple pure expressions.
- `SQLTranslationContext.definition_meta` already records definition CQL type,
  row shape, value column, and SQL result hints such as `Quantity`.
- Local probes show useful metadata for primitives, dates, quantities, lists,
  and intervals, but tuple selectors currently infer as `Any`, and lists of
  tuples infer as `List<Any>`. The facade cannot treat runtime JSON/VARCHAR
  transport as sufficient type evidence.
- There is no existing HTTP server dependency or general server namespace.
- The CLI uses `argparse`; adding a server command should follow that style.

## Architecture

Add a CQL-specific facade under `fhir4ds/cql/fhir_server/`.

Proposed modules:

- `types.py`: dataclasses for `CQLTypeRef`, `CQLResultMetadata`,
  `CQLEvaluationResult`, `CQLServerConfig`, and classified facade errors.
- `parameters.py`: dependency-free FHIR `Parameters` parsing/building utilities.
- `expression_service.py`: wraps a raw `$cql` expression into a one-definition
  CQL library, runs the translator/DuckDB path, and returns value plus metadata.
- `result_serializer.py`: converts typed CQL values into FHIR R4
  `Parameters.parameter` entries.
- `operations.py`: `handle_cql_operation(body, config)` pure function.
- `app.py`: small dependency-free HTTP server adapter for local runner use.
- `__init__.py`: exports only the stable service/app construction API.

Keep translator changes minimal:

- Add a public way to obtain result metadata for a translated definition, either
  `CQLToSQLTranslator.get_definition_meta(name)` or an equivalent immutable
  execution result object.
- Improve type metadata only where needed for facade serialization, especially
  tuple selectors, interval point types, list element types, temporal precision,
  and clinical/quantity/ratio JSON shapes.
- Do not add HTTP handling, FHIR `Parameters`, or runner-specific code to the
  translator package internals.

## Dependency Strategy

V1 should add no mandatory runtime HTTP dependency.

Use a dependency-free `ThreadingHTTPServer` adapter for local harness execution.
The core operation handler remains a pure Python function so future FastAPI,
Starlette, Flask, or ASGI adapters can wrap it without changing evaluation
logic. If a future implementation chooses FastAPI, it must be an optional extra
and the release gate must verify wheel metadata.

## Request Contract

Supported V1 endpoints:

- `POST /$cql`
- `POST /fhir/$cql`
- `GET /health`
- `GET /metadata` with a minimal CapabilityStatement-like response only if
  needed by tooling. The runner does not currently require it.

Request parsing rules:

- Require JSON object with `resourceType: "Parameters"`.
- Require exactly one top-level parameter named `expression` with a non-empty
  `valueString`.
- Accept but explicitly validate unsupported `$cql` parameters. `subject`,
  `library`, `data`, `prefetchData`, `dataEndpoint`, `contentEndpoint`, and
  `terminologyEndpoint` return an `OperationOutcome` in V1 unless implemented
  by a later approved slice.
- For nested input `parameters`, implement a typed parser matching `$cql`
  semantics where repeated names become lists and `part` becomes tuple data.
  The first acceptance slice may support only primitive, temporal, Quantity,
  Ratio, Code, Concept, Interval, List, Tuple, null, empty list, and empty tuple
  shapes that can be represented as static CQL parameter defaults.

## Evaluation Strategy

Create a synthetic library per request:

```cql
library FHIR4DSCqlRunner version '1.0.0'
using FHIR version '4.0.1'
parameter "<input-name>" <inferred-type> default <literal> // if supplied
define "return":
  <request expression>
```

Evaluation steps:

1. Parse the synthetic library with `parse_cql`.
2. Create a fresh DuckDB connection per request by default, register CQL UDFs,
   and run `CQLToSQLTranslator.translate_library_to_sql(..., "return")`.
3. Execute the SQL and require exactly one result column. Multiple rows are a
   serializer gap unless metadata says the expression is a list represented as
   rows.
4. Read immutable `DefinitionMeta` for `"return"` and construct
   `CQLResultMetadata`.
5. Return normal CQL nulls as a `return` parameter with the data-absent
   extension. Return engine failures as `evaluation error` with
   `OperationOutcome`.

DuckDB connections must not be shared across request threads unless a lock or
pool is implemented deliberately.

## Result Serialization

Serializer input is `(value, CQLResultMetadata)`, not a raw DuckDB type.

Minimum mapping:

- `Boolean` -> `valueBoolean`
- `Integer` -> `valueInteger`
- `Long` -> `valueDecimal` plus `cqf-cqlType: System.Long` until a better
  runner-compatible R4 representation is proven
- `Decimal` -> `valueDecimal`
- `String` -> `valueString`
- `Date` -> `valueDate`
- `DateTime` -> `valueDateTime`
- `Time` -> `valueTime`
- `Quantity` -> `valueQuantity { value, unit, system, code }`
- `Ratio` -> `valueRatio { numerator, denominator }`
- `Code` -> `valueCoding`
- `Concept` -> `valueCodeableConcept`
- `Interval<Date|DateTime|Time>` -> `valuePeriod` plus `cqf-cqlType`
- `Interval<Quantity>` -> `valueRange` plus `cqf-cqlType`
- `Interval<Integer|Decimal|Long>` -> `valueRange` where bounds are Quantity
  with unit `1`, plus `cqf-cqlType`
- `List<T>` -> repeated `return` parameters for top-level lists; nested lists
  use `part` entries named `element`
- `Tuple` -> one `return` parameter with named `part` entries
- `null` -> `_valueBoolean.extension` data-absent-reason unknown
- empty list -> `cqf-cqlType` plus `_valueBoolean.extension` `cqf-isEmptyList`
- empty tuple -> `cqf-cqlType` plus `_valueBoolean.extension` `cqf-isEmptyTuple`
- evaluation errors -> parameter named `evaluation error` with an embedded
  `OperationOutcome`

## Runner Harness

Add `conformance/scripts/run_cql_tests_runner.py`.

Script behavior:

- Start the local `$cql` facade on a free localhost port.
- Use either:
  - `CQL_TESTS_RUNNER_PATH` pointing to a user clone; or
  - Docker image `hlseven/quality-cql-tests-runner:<tag>`; or
  - a temporary pinned clone in `.temp`/CI cache.
- Do not add the runner as a git submodule in V1.
- Generate a runner config with `BaseUrl` pointing at the local facade and
  `CqlOperation: "$cql"`.
- Support `--quick`, `--only testsName:groupName:testName`, and
  `--runner-ref`.
- Write `conformance/reports/cql_tests_runner_report.json`.
- Report unsupported cases explicitly by category instead of hiding them as
  generic skips.

## Implementation Plan

1. Add `fhir4ds/cql/fhir_server/` package with typed errors and public
   operation/service dataclasses.
2. Add `parameters.py` request parser and response builder.
3. Add `expression_service.py` to evaluate expression-only synthetic libraries
   with fresh DuckDB connections and UDF registration.
4. Add public translator metadata access and close tuple/list/interval metadata
   gaps needed by serializer tests.
5. Add `result_serializer.py` with type-driven scalar, clinical, quantity,
   ratio, interval, list, tuple, null, empty, and error mappings.
6. Add dependency-free HTTP adapter and CLI command, tentatively
   `fhir4ds cql-server --host 127.0.0.1 --port 8080 --base-path /fhir`.
7. Add `conformance/scripts/run_cql_tests_runner.py`.
8. Add docs for the facade, conformance harness, and result-type matrix.
9. Run focused tests, CQL tests, full conformance, runner smoke, and release
   artifact validation.

## Test Strategy

Unit tests:

- Request parser accepts runner expression body and rejects malformed
  `Parameters`.
- Input parameter parser covers primitive, temporal, clinical, quantity, ratio,
  interval, list, tuple, null, empty list, and empty tuple shapes.
- Serializer covers every mapping above, matching the runner extractor shapes.
- `OperationOutcome` builder avoids leaking full request bodies or CQL payloads
  unless debug mode is enabled.

Integration tests:

- End-to-end `$cql` requests for primitive arithmetic, Date/DateTime/Time,
  Quantity, Ratio, Code, Concept, Interval, List, Tuple, null, and empty values.
- CLI launches server and responds to local HTTP POST.
- Runner smoke using `OnlyList` or `--quick`.

Regression tests:

- Existing CQL translator and DuckDB macro/UDF parity tests.
- `python3 conformance/scripts/run_all.py`.
- Wheel metadata/import check if CLI, package exports, or dependencies change.

## Open Decisions For Self-Audit

- Whether the first implementation slice supports input `$cql` parameters fully
  or only parses/reports unsupported shapes.
- Whether Long should be serialized as decimal plus `cqf-cqlType`, string plus
  extension, or a runner patch is needed.
- Whether tuple and list type metadata can be fixed narrowly without disturbing
  existing measure translator behavior.
