# CQL-01 EXPLORER Engineer Handoff

## Remediation Summary

- Added direct FHIRPath primitive runtime type helpers in `fhir4ds/cql/translator/expressions/_query.py` and routed primitive `is`/`as` through FHIRPath `type().name` where the source is a direct FHIRPath UDF value.
- Routed `ToInteger`, `ToDecimal`, `ToBoolean`, and `convert ... to <primitive>` through spec-aware DuckDB macros/UDFs instead of generic DuckDB casts.
- Tightened CQL numeric lexing to reject no-whitespace suffix junk after numeric literals.
- Extended CQL type inference so simple retrieve property returns carry primitive CQL type metadata into materialized query definitions, then used that metadata for later primitive `is`/`as`.
- Updated unit and integration tests to assert the spec-aware conversion/function behavior and native-loaded versus forced Python fallback parity.

## Changed Areas

- `fhir4ds/cql/translator/expressions/_query.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/inference.py`
- `fhir4ds/cql/parser/lexer.py`
- `fhir4ds/cql/duckdb/macros/conversion.py`
- `fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`
- `fhir4ds/cql/tests/unit/test_v2_expressions.py`

## Notes

The conversion-function lowering change is intentional. Unit tests should expect `SQLFunctionCall("ToInteger" | "ToDecimal" | "ToBoolean")` for spec-aware conversions rather than `SQLCast`.

The `1 garbage` shape was not treated as a numeric suffix bug because whitespace separates tokens and the query grammar may interpret an expression plus alias; the lexer guard only rejects suffix characters that immediately follow the numeric literal.
