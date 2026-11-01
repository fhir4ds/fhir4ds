# Engineer Handoff — CQL-01, iteration 1

All six QA issues RESOLVED with focused regression tests
(fhir4ds/cql/tests/unit/test_cql01_primitive_types.py, 20 tests, all passing).

## Fixes
- QA-001 (overflow→null): typed extent literals (CAST AS INTEGER/BIGINT) in
  `_translate_maximum_pre`/`_translate_minimum_pre` (_functions.py) + DuckDB
  `TRY(...)` wrap for function-call-free integral +,-,* with at least one
  runtime operand (_operators.py, `_integral_static_operand_types` +
  `_contains_function_call` helpers).
- QA-002 (decimal extent concat): extents emit numeric `SQLLiteral`
  (Decimal value, unquoted raw_sql); `_is_numeric_typed` accepts Decimal.
  Result limited to DECIMAL(38,8) (spec permits implementation precision ≥ 28).
- QA-003: ToDecimal macro regexp `\.[0-9]+` + TRY_CAST rounds to scale 8.
- QA-004: parser rounds >8-fractional-digit Decimal literals (ROUND_HALF_UP,
  raw_str carries limited value); >28 integer digits still an error.
- QA-005: Truncate macro → `TRY_CAST(system.trunc(x) AS INTEGER)` in BOTH
  fhir4ds/cql/duckdb/macros/math.py and the shared
  fhir4ds/fhirpath/duckdb/macros/math.py — the FHIRPath macro registration
  runs later and previously clobbered the CQL macro with trunc-only SQL.
- QA-006: CanConvert(x, T) translator lowering to ConvertsToT; unknown target
  types raise TranslationError (no silent passthrough).

## Validation
- Full conformance gate: **2832/2832** (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47). Baseline held.
- CQL unit+integration: 1801 passed, 4 skipped.
- fhirpath/duckdb pytest: 1758 passed, 7 failed — all pre-existing
  native-extension regex parity failures (replaceMatches/matches named-group
  and multiline-anchor cases; native C++ path returns empty). Unrelated to
  this chunk (no C++ sources touched); the FHIRPath conformance gate is
  935/935. Flagged for the FP native surface owner.

## Recovery-gate event (documented)
First TRY-wrap attempt regressed DQM (Binder: "TRY can not be used in
combination with a volatile function" — Python UDFs are volatile) and 3 CQL
literal tests (runner only accepted error/NULL for invalid="true" while the
official fixture comment for DecimalTenthStep also accepts "round to a whole
step"). Fixed by restricting TRY to function-call-free arithmetic and
extending conformance/scripts/run_cql.py to accept the fixture-sanctioned
rounded-literal result (comparison against the literal quantized to 10^-8,
not a blanket acceptance of non-NULL invalid results).
