# Engineer Handoff — CQL-11 SKEPTIC (iteration 1)

All three confirmed issues fixed at root cause, dual-engine where required.

## QA-001 (HIGH) TruncatedDivide exactness/typing — VERIFIED
- Root cause: `_operators.py` div lowering emitted `TRUNC(a / NULLIF(b,0))`;
  DuckDB `/` promotes to DOUBLE → 0.3 div 0.1 = 2, Long-range inexact,
  Long overflow not null, DOUBLE result type for Integer operands.
- Fix: exact `cqlDivide` core (scale-8 exact division, null on zero divisor)
  + `TRUNC` + typed `TRY_CAST` narrowing dispatched on
  `_infer_static_numeric_type` (Integer pair → INTEGER, Long pair → BIGINT,
  Decimal/dynamic → DECIMAL(38,8) core). Mirrors the `^` operator pattern.
- Hazard guard: `_translate_coalesce`'s `_is_numeric_expr` now unwraps
  TRUNC so DECIMAL div results participate in COALESCE numeric normalization.
- Stale unit test `test_integer_division_div` (pinned old DOUBLE shape)
  updated to the exact core.

## QA-002 (MEDIUM) Power underflow — VERIFIED
- Root cause: `mathPower` `%.15g` scientific output text; DuckDB
  VARCHAR→DECIMAL(38,8) cast rounds '9.09e-10' UP to 1E-8.
- Fix: both `fhir4ds/cql/duckdb/udf/math.py::mathPower` and native
  `extensions/cql/src/cql/math.cpp::math_power` emit fixed `%.8f` for
  0<|v|<1e-4. Extension rebuilt and md5-verified (build, repo bundle,
  site-packages: c334f120fb3ebff64af548bd189068cc).

## QA-003 (MEDIUM) Precision(5) engine divergence — VERIFIED
- Root cause: translator passed raw INTEGER literal to VARCHAR-only native
  CQLPrecision.
- Fix: Precision literal branch now covers Decimal/Integer/Long and passes
  raw VARCHAR text to CQLPrecision on both engines (→ 0).

## Validation
- Reproducers (.temp/qa/probe*.py) all pass on both engines.
- CQL unit tests: 1612 passed. DuckDB integration suite: 827 passed,
  5 skipped. Full conformance: 2832/2832 (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47) — baseline holds.
- New regression tests in test_arithmetic_part2_parity.py (3 tests).
- AGENTS.md doctrine entry added (CQL-11 SKEPTIC doctrine).
