# QA Handoff — FP-18 SKEPTIC iteration 1 (2026-08-18)

Chunk: FHIRPath §6.6 Math Operations + §6.7 Date/Time Arithmetic
(div, mod, &, dateTime +/-, numeric corners not covered by FP-01/FP-02/FP-07).

## Method
Three-engine probe matrix: Python core `evaluate()`, native C++ DuckDB extension
(LOAD extensions/fhirpath/build/release/repository/v1.5.2/.../fhirpath.duckdb_extension),
Python-fallback DuckDB UDF. Spec text pulled from hl7.org/fhirpath/N1 §6.6–§6.7 and
official R4 fixture XML (tests-fhir-r4.xml) extracted for div/mod/&.

## Verified as correct (no issue)
- div/mod truncation toward zero incl. negative operands: -5 div 2 = -2, -5 mod 2 = -1, 5 mod -2 = 1 — all 3 engines agree (§6.6.5/6 truncated semantics).
- Decimal div/mod fixtures: 5.5 div 0.7 = 7, 5.5 mod 0.7 = 0.6, 2.2 mod 1.8 = 0.4, 10.0 mod 4.0 = 2.0 — agree.
- div/mod by zero → empty on all engines (fixtures testDiv5/testMod5).
- Boolean operands rejected (`true div 1` error/empty) per FP-18 prior doctrine.
- `&` empty→empty-string semantics (`'a' & {}` = 'a') and non-string singleton conversion (`1 & 'b'` = '1b', `true & 'x'`) — engines agree, fixtures testConcatenate1–3 pass shape.
- dateTime − dateTime / Time − Time not defined by §6.7.2 (right operand must be Quantity) → error/empty everywhere. Correct.
- Calendar arithmetic: month/year clamping (@2019-01-31+1 month=2019-02-28, @2020-02-29+1 year=2021-02-28), @2014-24 months=@2012, weeks, timezone-carrying operand @2015-02-04T14:34:28+10:00+1 hour, partial precision @2012-01-01T10+90 minutes=@2012-01-01T11, decimal-portion ignored (@2012-01-01+1.5 days=@2012-01-02), Time ± minutes, Date+hours and Time+days rejected per §6.7.1 unit lists — all engines agree.

## Issues logged (evolution.json)
- QA-001 MEDIUM: unsuffixed Integer literal > INT32_MAX: core returns value; native throws "Integer literal out of range" (→ empty); fallback empty. Lockstep + N1 §22.1 divergence.
- QA-002 HIGH: div/mod computed via binary64 — 64-bit operands silently wrong on all engines (9223372036854775807L div 1 → ...808 PY/FB; 2305843009213693951L mod 7 → 2 NAT, correct 1).
- QA-003 MEDIUM: native div on 64-bit results renders scientific notation (4.6116860184273879e+18) violating §5.5.8; value rounded.
- QA-004 MEDIUM: 28-digit Decimal mod: native 0.0 (fmod precision loss) vs exact 1e-29 in PY/FB.
- QA-005 MEDIUM: Python core leaks raw TypeError (Quantity operands to div/mod) and ValueError (Date + hours / Date + 'a') instead of FHIRPathError.

## Reproducer base
.temp/qa probe scripts; see evolution.json evidence lines for exact expressions.
