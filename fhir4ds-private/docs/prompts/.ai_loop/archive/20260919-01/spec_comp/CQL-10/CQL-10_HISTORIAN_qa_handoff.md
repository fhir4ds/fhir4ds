# QA Handoff — CQL-10 HISTORIAN, iteration 1 (2026-08-21)

Chunk: CQL 1.5 Arithmetic Operators Part 1 — Abs, Add, Ceiling, Divide, Floor,
Exp, Log, Ln, HighBoundary, LowBoundary. Personality: HISTORIAN. All probes
dual-path (Python supplements vs C++ extension); **zero py↔cpp divergence** on
every case. Probes: `/mnt/d/fhir4ds/.temp/qa/cql10_historian/probe{1,2}.py`
(discovery) and `probe{3,4}.py` (reproducers).

## SKEPTIC fix re-verification — all 5 intact and spec-correct

- High/LowBoundary Decimal fill-and-truncate verified against the **live HL7
  reference implementation**
  (cqframework/clinical_quality_language `main`,
  `HighBoundaryEvaluator.kt`/`LowBoundaryEvaluator.kt`): our semantics are
  byte-equivalent — High appends `99999999` then `setScale(p, DOWN)`, Low is
  `setScale(p, DOWN)` (DOWN = toward zero, so negatives are CORRECT:
  LowBoundary(-1.587,2) = -1.58, HighBoundary(1.587,0) = 1). This closes the
  open review REV-030-002 concern (negative/low-precision handling) for the
  decimal surface.
- Temporal boundary precision-range mapping matches reference
  `expandPartialMax` semantics (HighBoundary(@2014) = @2014 because
  expandPartialMax(YEAR) fills month/day with MINIMUMs; (@2014,6)→@2014-12;
  (@2014-01-01T08,17)→08:59:59.999; (@T10:30,9)→59.999; precision>max → null).
- Ceiling/Floor Integer-extent nulls, Integer+Long BIGINT promotion (Add,
  Subtract, Multiply), Abs static-integral narrowing, Exp/Ln/Log
  DECIMAL(38,8) — all re-verified correct on both backends.
- Verified clean (no issues): Add/Sub/Mul overflow→null both engines; Divide
  exact-decimal incl. Long/Long and div-by-zero→null; Exp/Ln/Log domain
  errors→null and DECIMAL scale-8 rendering; Abs min-Long→null; bare-vs-Quantity
  arithmetic Add/Sub/Div→null, Mul/Div-by-scalar quantity composition;
  temporal boundaries; Long inputs through decimal overloads.
- HARNESS TRAP (recorded): appending `::VARCHAR` directly after generated SQL
  binds tighter than `+` (`a + b::VARCHAR`) and fabricates Binder errors —
  wrap generated SQL in parentheses before casting.

## New issues (logged in evolution.json)

1. **QA-001 HIGH** — Decimal High/LowBoundary translated results degrade to
   DOUBLE: `TRY_CAST(CAST(HighBoundary(...) AS VARCHAR) AS DOUBLE)`.
   `HighBoundary(123456789012345678901234.5, 8)` → `1.2345678901234569e+23`
   (expected exact `123456789012345678901234.59999999`); official fixture
   LowBoundaryDecimal expects scale-8 text `1.58700000`, current DOUBLE path
   renders `1.587`. Same translator seam SKEPTIC fixed for Exp/Ln/Log
   (DECIMAL(38,8)); boundary branch was missed.
2. **QA-002 MEDIUM** — inconsistent static wrong-type taxonomy across the
   chunk operator family: Add raises typed TranslationError, but Divide
   silently nulls (`'x' / 2`, `1 / 'x'`), Exp/Ln/Log/High/LowBoundary silently
   null on String first arg, Abs/Floor/Ceiling leak raw BinderException,
   HighBoundary(1.587,'x') leaks a raw Conversion Error. Violates the
   typed-exception / no-silent-fallback contract.

## Spec verification

Fetched and quoted the reference implementation sources for
High/LowBoundaryEvaluator.kt and Date.kt expandPartialMax (raw GitHub, main
branch); official fixtures from
`fhir4ds/cql/tests/official/cql-tests/tests/cql/CqlArithmeticFunctionsTest.xml`
(HighBoundaryDecimal 1.58799999, LowBoundaryDecimal 1.58700000).

Baseline conformance run deferred to the FIX-phase recovery gate.
