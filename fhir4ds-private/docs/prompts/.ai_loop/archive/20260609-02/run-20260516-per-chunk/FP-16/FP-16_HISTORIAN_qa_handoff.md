# QA Handoff - FP-16 HISTORIAN

## Scope

Fresh §6.4 Collections audit from current code and the normative FHIRPath N1 spec:
- `|` / `union()` collection merge and duplicate elimination
- `in` membership
- `contains` containership

Spec anchors checked:
- §6.4.1: `|` merges collections and eliminates duplicate values using `=` equality semantics.
- §6.4.2: `in` requires singleton left operand, returns empty for empty left, false for empty right, and uses equality semantics.
- §6.4.3: `contains` is the converse: singleton right operand, empty for empty right, false for empty left, and equality semantics.
- §6.1.1 Quantity Equality: compatible Quantity dimensions compare by value even when units differ; `1 cm` and `10 mm` are equal when UCUM conversion is supported.

## Probes

Compared native C++ DuckDB extension and forced Python fallback public UDF surfaces using:
- `fhirpath`
- `fhirpath_json`
- `fhirpath_bool`

Covered:
- empty operand behavior for `in`/`contains`
- multi-item operand resilience on public UDFs
- numeric duplicate elimination (`1 | 1.0`)
- structural object equality independent of member order
- temporal equality for Date, Time seconds/milliseconds, and DateTime timezone normalization
- FHIR `Observation.valueQuantity` / `component.valueQuantity` path values in `=`, `in`, `contains`, `|`, and `union()`
- adjacent Python direct operator helpers in `fhir4ds.fhirpath.duckdb.operators`

## Findings

### QA-001 - HIGH - Native §6.4 collection operators missed FHIR Quantity path equality

Native `value = component.value` returned true for compatible FHIR Quantity paths, but native collection operators did not reuse that materialization/equality behavior:

```text
valueQuantity = 1 cm
component.valueQuantity = 10 mm

value = component.value                  native true, fallback true
value in component.value                 native false, fallback true
component.value contains value           native false, fallback true
(value | component.value).count()        native 2, fallback 1
value.union(component.value).count()     native 2, fallback 1
```

Root cause candidate: `extensions/fhirpath/src/fhirpath/evaluator.cpp::fpValuesEqual()` checked raw `JsonVal` equality before Quantity-like JSON materialization, while ordinary equality/comparison paths materialized Quantity-like JSON operands first.

## Validation Run During QA

After remediation source edits and bundled extension refresh, focused validation passed:

```bash
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py -q
# 116 passed in 3.09s
```

The focused native/fallback repro also passed after rebuild/copy:

```text
native_loaded=True, fallback_loaded=False
All tested Quantity collection expressions matched between native and forced Python fallback.
```
