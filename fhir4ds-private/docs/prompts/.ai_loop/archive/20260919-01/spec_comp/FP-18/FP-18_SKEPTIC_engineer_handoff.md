# Engineer Handoff — FP-18 SKEPTIC iteration 1 (2026-08-18)

## Fixes (all RESOLVED; QA-006 DEFERRED)

### QA-001 Integer/Long literal range lockstep
- `fhir4ds/fhirpath/engine/evaluators/__init__.py` `number_literal`: unsuffixed
  Integer literals outside [-2^31, 2^31-1] now raise `FHIRPathError("Integer
  literal out of range")` (N1 §22.1; native already throws; both DuckDB paths
  return empty). Long (`L`) literals outside int64 raise "Long literal out of
  range". No official fixture uses >INT32 unsuffixed literals (verified).

### QA-002/QA-003 Exact truncated div/mod
- `fhir4ds/fhirpath/engine/invocations/math.py`: `intdiv`/`mod` now use exact
  integer truncated division (`_truncated_divmod_int`: floor then adjust
  toward zero) and exact Decimal `//` (Decimal floordiv truncates toward zero)
  instead of `int(x / y)` / `int(dx / dy)` binary64 round-trips.
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`: new exact int64 div/mod
  path for Integer-typed operands (Integer and Long literals) — int64 division
  truncates toward zero; LLONG_MIN / -1 guarded (mod = 0, div throws overflow);
  results via `FPValue::FromInteger` so 64-bit quotients render as plain
  integers (fixes scientific-notation §5.5.8 violation).
- Extension rebuilt (`make release`), deployed to
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` (repo bundle).

### QA-004 Exact Decimal mod (native)
- `tryDecimalModExactText`: __int128 decimal-text truncated mod from operand
  source_text, aligned exponents, checked scaling; bails to binary64 fmod on
  overflow/exponent forms. Exact remainder text preserved as `source_text`
  (e.g. 0.00000000000000000000000000001).

### QA-005 Error contract
- `intdiv`/`mod` raise `FHIRPathError` for Quantity operands (§6.6.5/§6.6.6
  Integer/Decimal only) instead of leaking raw TypeError.
- New `_temporal_plus` wrapper converts `ValueError` from
  `FP_TimeBase.plus` (invalid §6.7.1 units: Date+hours, Time+days, UCUM 'a')
  to `FHIRPathError` at both `+` and `-` operator boundaries.

### QA-006 (DEFERRED) — `/` rendering divergence
- Native `1 / 3` renders 16-digit shortest-round-trip vs fallback's 28-digit
  Decimal context. Numeric equality agrees; no fixture pins rendering; fix
  requires porting decimal-context division to C++. Logged, deferred.

## Validation
- New regression tests: `fhir4ds/fhirpath/tests/unit/test_fp18_math_operators.py`
  — 53 passed (value tests, literal-range, error contract, calendar arithmetic,
  and native-vs-fallback parity tests with auto-skip).
- Full package pytest: see architect handoff (all green).
- Conformance master gate: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 — OVERALL 2832/2832 (no regression).
