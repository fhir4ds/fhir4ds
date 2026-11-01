# Engineer Handoff - CQL-07 SKEPTIC

## Fixed Issue

`QA-001` resolved. Quantity string conversions now reject invalid unit designators. The fix applies to:

- Python `ToQuantity`/`ConvertsToQuantity`
- Python `ToRatio`/`ConvertsToRatio` through shared `toQuantity`
- Direct native C++ `cql::to_quantity`

Valid UCUM/Pint-supported units and CQL calendar duration keywords remain accepted.

## Files Changed

- `fhir4ds/cql/duckdb/udf/quantity.py`
- `extensions/cql/src/cql/quantity.cpp`
- `extensions/cql/test/sql/cql.test`
- CQL conversion parity tests under `fhir4ds/cql/duckdb/tests/integration/`
- Refreshed bundled CQL extension at `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`

## Validation

- Focused conversion parity pytest: 6 passed.
- Native CQL extension SQL tests: 620 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Bundled CQL extension SHA matches build output: `c5061959200166cf329560a0a05e6f928c4866035e0dd5f9e54aabf06c343f7d`.
