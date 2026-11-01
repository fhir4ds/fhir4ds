# Engineer Handoff — CQL-11 HISTORIAN (iteration 1)

Both OPEN issues fixed at root cause, dual-engine verified.

## QA-001 (HIGH) Round/RoundTo FLOOR-override corruption — RESOLVED
- Root cause: `fhir4ds/cql/duckdb/macros/math.py` Round/RoundTo macro
  bodies called bare `FLOOR`/`CEIL`. `Floor(x)` is overridden in the same
  registration as the CQL Floor macro (`TRY_CAST(system.floor(x) AS
  INTEGER)`), so the positive rounding branch silently narrowed through
  INTEGER: any value whose shifted magnitude exceeded 2^31 rounded to
  NULL (`RoundTo(123.456, 8)` -> NULL, `Round(3147483647.05)` -> NULL).
  Negative branch (CEIL) was unaffected — a diagnostic tell.
- Fix: `system.floor`/`system.ceil` + `TRY_CAST(... AS DECIMAL(38,8))`
  (CQL Round returns Decimal; only Decimal-unrepresentable results are
  null). Macro is Python-registered on both the native and supplement
  paths, so one fix covers both engines; no C++ rebuild required.

## QA-002 (HIGH) Decimal arithmetic overflow raises — RESOLVED
- Root cause: `_operators.py` overflow guards were Integer/Long-only
  (`_static_integer_arithmetic_overflows` literal fold +
  `_integral_static_operand_types` runtime TRY guard). Decimal literal
  products beyond DECIMAL(38,8) reached DuckDB and raised
  OutOfRangeException.
- Fix: added `_decimal_static_arithmetic_unrepresentable` (exact Decimal
  evaluation of +,-,* literal trees; >= 10^30 integer-digit extent folds
  to NULL — DECIMAL(38,8) has 30 integer digits; excess fractional scale
  still rounds per CQL-01 doctrine) and widened the runtime TRY guard via
  `_numeric_static_operand_types` (Integer/Long/Decimal). All existing
  TRY-guard exclusions preserved (function-call-free, no subqueries, no
  aggregate lambdas).

## Validation
- Probe `/mnt/d/fhir4ds/.temp/qa/cql11_historian2_probe.py`: both real
  issues clean on python + native engines; remaining diffs are the four
  spec-verified INTENDED behaviors (see qa_handoff.md).
- `test_arithmetic_part2_parity.py`: 15/15 (2 new tests:
  `test_cql_round_macro_survives_integer_range_shift_cql11_historian2`,
  `test_cql_decimal_multiply_overflow_is_null_cql11_historian2`).
- Full conformance: 2832/2832 — ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47. Baseline holds.
- No files edited outside macros/math.py, _operators.py, and the parity
  test file. No extension rebuild needed (Python macro layer only).
