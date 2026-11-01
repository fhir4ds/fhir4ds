# QA Handoff — CQL-10 SKEPTIC, iteration 1 (2026-08-21)

Chunk: CQL 1.5 Arithmetic Operators Part 1 — Abs, Add, Ceiling, Divide, Floor,
Exp, Log, Ln, HighBoundary, LowBoundary. Probed via `translate_cql` end-to-end
and direct DuckDB execution on BOTH the Python-only connection
(`_register_python_supplements(cpp_loaded=False)`) and the C++ extension path
(`register()`). Zero native↔Python parity drift observed on any probe — all
five findings reproduce identically on both backends.

Probes: `/mnt/d/fhir4ds/.temp/qa/cql10/probe{1..7}.py`.

## Spec verification (cql.hl7.org 2020May 09-b-cqlreference §Arithmetic + §6.7/§6.9; v2 reference for clarifying examples)

- Add: mixed Integer/Long → Integer implicitly converted to Long; overflow → null.
- Abs: Abs(Integer)→Integer; "if the absolute value cannot be represented (e.g. Abs(minimum Integer)) the result is null".
- Ceiling/Floor(Decimal)→Integer; "If the result cannot be represented as an Integer, the result is null" (v2 examples: Ceiling(3147483647.05)→null, Floor(2147483648.2)→null).
- Exp/Ln/Log(argument Decimal)→Decimal; Integer/Long implicitly converted to Decimal.
- HighBoundary/LowBoundary: "greatest/least possible value of the input to the specified precision" — v2 example HighBoundary(1.587, 2)//1.59, LowBoundary(1.587, 2)//1.58. No Quantity overload exists (Quantity input → null is correct).
- Arithmetic header rule: overflow/underflow → null, never a run-time error.

## Issues found (all logged in evolution.json)

1. QA-001 HIGH — HighBoundary/LowBoundary Decimal precision semantics wrong when precision < current decimal places: `HighBoundary(1.587, 2)` → 1.587 (expected 1.59); `LowBoundary(1.587, 2)` → 1.587 (expected 1.58); precision 0 → unchanged (expected 2 / 1). Correct semantics: bucket boundary at the requested precision (floor at precision for Low; floor+10^-precision for High when precision<8; fill-9s to scale 8 at precision 8). Present in Python UDF (`fhir4ds/cql/duckdb/udf/math.py::_decimal_boundary_text` + int/float branches of highBoundary/lowBoundary) AND C++ `extensions/cql/src/cql/boundary.cpp::high_boundary/low_boundary` numeric paths. Negative-operand floor/ceil direction must be correct too.
2. QA-002 HIGH — Ceiling/Floor Integer-extent null rule missing: `Ceiling(3147483647.05)` → 3147483648 (expected null), `Floor(2147483648.2)` → 2147483648 (expected null), `Ceiling(1e23)` → 10^23 (expected null). Both macro path (`macros/math.py` Ceiling/Floor) and translator literal folding path.
3. QA-003 HIGH — Add Integer↔Long implicit promotion missing: `1 + 2147483647L` and `2147483647L + 1` raise DuckDB OutOfRangeError (INT32 overflow) instead of returning Long 2147483648. Integer+Integer and Long+Long overflow already null correctly; the mixed-type case loses the Long type in SQL generation (`1 + 2147483647` — no BIGINT cast, no overflow guard).
4. QA-004 MEDIUM — Abs typed-overflow guard only covers literal AST shapes: `Abs(-2147483648 - 0)` → 2147483648 (expected null). Static Integer-typed operands must be range-guarded; Long analogue `Abs(-9223372036854775807L - 1L)` already returns null correctly.
5. QA-005 MEDIUM — Exp/Ln/Log return DOUBLE, not Decimal: translator emits `TRY_CAST(mathExp(...) AS DOUBLE)`; `Exp(1)` → 2.71828182845905, expected Decimal scale-8 → 2.71828183 per CQL-01 exact-Decimal doctrine and spec return type Decimal. Same for Ln, Log (`system.log`).

## Verified correct (NOT A BUG additions appended to fhir4ds/cql/AGENTS.md)

- Abs(Quantity) preserves unit; quantity add unit-space composition (1 'g' + 500 'mg' → 1500 'mg' both orders); Divide exact-Decimal (9.9/3.0=3.3, 1/3=0.33333333, div-by-zero→null); Ceiling/Floor rounding directions incl. negatives; Exp(1000)/Ln(0)/Ln(-1)/Log domain errors → null; HighBoundary/LowBoundary temporal paths and default precision (HighBoundary(0.1)→0.19999999); mixed Integer+Decimal Add (1+0.5→1.5); Log argument order (Log(8,2)=3); High/LowBoundary on Quantity input → null (spec has no Quantity overload).

Baseline CQL conformance rerun launched pre-fix (results in `.temp/qa/cql10/cql_baseline.log`).
