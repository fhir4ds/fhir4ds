# Engineer Handoff - CQL-06 SKEPTIC

## Fixed Issues

- `QA-001`: `ConvertsToBoolean` no longer treats decimal-looking or whitespace-padded strings as numeric Boolean overloads. String inputs now match only the CQL-listed Boolean strings.
- `QA-002`: `ConvertsToDecimal` and `ToDecimal` now enforce CQL decimal string syntax and accept Boolean conversion (`true` -> `1.00000000`, `false` -> `0.00000000`).
- `QA-003`: Date/DateTime conversion checks no longer stringify arbitrary numeric inputs. Native DuckDB `DATE`/`TIMESTAMP` values are handled by type, including DateTime-to-Date conversion.
- `QA-004`: Python `toQuantity()` and native C++ `cql::to_quantity()` now require at least one digit before the decimal point and reject exponent notation. Ratio conversion checks inherit the stricter quantity parser.

## Files Changed

- `fhir4ds/cql/duckdb/udf/conversion.py`
- `fhir4ds/cql/duckdb/udf/quantity.py`
- `fhir4ds/cql/duckdb/macros/conversion.py`
- `extensions/cql/src/cql/quantity.cpp`
- `extensions/cql/test/sql/cql.test`
- CQL DuckDB parity tests under `fhir4ds/cql/duckdb/tests/integration/`
- Refreshed bundled CQL extension at `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`

## Validation

- Focused parity pytest: 13 passed.
- Native CQL extension SQL tests: 616 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

All issues in `evolution.json` are marked `RESOLVED`.
