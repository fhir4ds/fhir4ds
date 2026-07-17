---
id: cql-tests-runner-facade
title: CQL Tests Runner Facade
sidebar_label: CQL Tests Runner Facade
draft: true
---

# CQL Tests Runner Facade

FHIR4DS includes a narrow FHIR R4 `$cql` facade for running
`cqframework/cql-tests-runner` against the local CQL engine. It is a
conformance harness, not a general FHIR server.

## Scope

The facade supports expression-only `$cql` requests:

```json
{
  "resourceType": "Parameters",
  "parameter": [
    { "name": "expression", "valueString": "1 + 2" }
  ]
}
```

It returns a FHIR `Parameters` resource with one or more `return` parameters.
Evaluation errors are returned as a `Parameters` resource containing parameter
name `evaluation error` with an embedded `OperationOutcome`, matching the
runner extractor.

Unsupported in the current facade:

- FHIR resource storage and search
- retrieve-backed CQL evaluation
- terminology server behavior
- `Library/$evaluate`
- external `dataEndpoint`, `contentEndpoint`, or `terminologyEndpoint` inputs

## Running Locally

Start the facade:

```bash
fhir4ds cql-server --host 127.0.0.1 --port 8080 --base-path /fhir
```

Then send `$cql` requests to either:

- `http://127.0.0.1:8080/$cql`
- `http://127.0.0.1:8080/fhir/$cql`

The operation handler can also be used directly:

```python
from fhir4ds.cql.fhir_server import CQLServerConfig, handle_cql_operation

status, body = handle_cql_operation(
    {
        "resourceType": "Parameters",
        "parameter": [{"name": "expression", "valueString": "1 + 2"}],
    },
    CQLServerConfig(use_cpp_extensions=False),
)
```

## Runner Harness

Use a local runner clone:

```bash
CQL_TESTS_RUNNER_PATH=/path/to/cql-tests-runner \
python3 conformance/scripts/run_cql_tests_runner.py --quick
```

Or pass an explicit path:

```bash
python3 conformance/scripts/run_cql_tests_runner.py \
  --runner-path /path/to/cql-tests-runner \
  --only CqlArithmeticFunctionsTest:Add:Add11
```

The script writes `conformance/reports/cql_tests_runner_report.json` and keeps
raw runner output under `conformance/reports/cql_tests_runner_raw/`.

## Result Type Matrix

| CQL type | FHIR Parameters representation |
| --- | --- |
| Boolean | `valueBoolean` |
| Integer | `valueInteger` |
| Long | `valueDecimal` plus `cqf-cqlType: System.Long` |
| Decimal | `valueDecimal` |
| String | `valueString` |
| Date | `valueDate` |
| DateTime | `valueDateTime` |
| Time | `valueTime` |
| Quantity | `valueQuantity` |
| Ratio | `valueRatio` |
| Code | `valueCoding` |
| Concept | `valueCodeableConcept` |
| Interval&lt;Date/DateTime/Time&gt; | `valuePeriod` plus `cqf-cqlType` |
| Interval&lt;Quantity/Integer/Decimal/Long&gt; | `valueRange` plus `cqf-cqlType` |
| List&lt;T&gt; | repeated parameters with the same name |
| Tuple | named `part` entries |
| null | `data-absent-reason` extension |
| empty list | `cqf-isEmptyList` extension |
| empty tuple | `cqf-isEmptyTuple` extension |

Open bounded intervals are reported as serializer gaps because the current
runner `Range` and `Period` extractors infer closed boundaries from the
presence of bounds and cannot faithfully compare open bounds.
