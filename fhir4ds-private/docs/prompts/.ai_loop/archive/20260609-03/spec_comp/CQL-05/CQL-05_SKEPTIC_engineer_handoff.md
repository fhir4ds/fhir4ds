# Engineer Handoff: CQL-05 SKEPTIC

## Fixed Issues

- `QA-001`: Added static type inference for `convert` expressions so
  `convert ... to Any` preserves the source runtime type for downstream
  `is`/`as` assertions, and non-Any conversion targets expose their structural
  result type.
- `QA-002`: Recognized `ToQuantity(...)` SQL expressions and CQL
  `convert ... to Quantity` ASTs as Quantity-shaped, so nested
  `convert Quantity to String` routes through `QuantityToString`.
- `QA-003`: Added composite `as` target inference for `List<T>`, `Interval<T>`,
  `Choice<...>`, and `Tuple { ... }`, preventing typed-null list assertions
  from falling through to generic FHIR `resourceType` probing.
- `QA-004`: Updated `QuantityToString` to normalize JSON numeric values through
  `DECIMAL(38, 8)` and trim trailing zeros while preserving at least one
  decimal digit, matching CQL Quantity string format.

## Changed Files

- `fhir4ds/cql/translator/expressions/_query.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/macros/conversion.py`
- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`
- `.temp/qa/cql05_skeptic_probe.py`
- `AGENTS.md`
- `extensions/cql/AGENTS.md`

## Validation

```bash
python3 .temp/qa/cql05_skeptic_probe.py
python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > validation_summary.log && cat validation_summary.log
```

Results:
- Fresh probe passed.
- Focused pytest: `28 passed`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`,
  CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.
