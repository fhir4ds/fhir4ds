# QA Handoff — CQL-10 EXPLORER, iteration 1 (2026-08-21)

Chunk: CQL 1.5 Arithmetic Operators Part 1 — Abs, Add, Ceiling, Divide, Floor,
Exp, Log, Ln, HighBoundary, LowBoundary. Personality: EXPLORER. Probes:
`/mnt/d/fhir4ds/.temp/qa/cql10_explorer/probe{1,3,4}.py` (probe.py/probe2.py/
results.json are leftovers from an interrupted prior EXPLORER attempt on this
chunk; preserved, not re-run). Zero py↔cpp divergence on every case.

## Verified clean (no issues)

- Quantity Add/Sub with unit conversion (1 'mg' + 0.001 'g' → 2 'mg'; both
  directions; decimal operands; negatives); incompatible units → null both
  engines.
- Abs(Quantity) preserves unit and sign handling (-5 'mg' → 5 'mg').
- Quantity/Quantity Divide: like units → unit '1' (matches official fixture
  Divide1Q1Q); right-unit '1' → keeps left unit; spec example 12 'cm2' /
  3 'cm' → 4.0 'cm' (exponent simplification works); div-by-zero → null.
- Multiply: scalar×Quantity and Quantity×scalar both scaled correctly;
  Q×Q → derived unit ('mg2').
- TruncatedDivide quantity fixtures: 10.0 'g' div 5.0 'g' → 2.0 'g';
  10.1 'cm' div -3.1 'cm' → -3.0 'cm'; div by 0 → null.
- Temporal boundaries: HighBoundary(@2024,4)/(@2024-01,4)/(@2024-01,8) →
  2024/2024/2024-01-31; (@2024-01-01T08,17) → 08:59:59.999; (@T10:30,9) →
  59.999; precision > max (99) → null; null input → null; default precision.
  LowBoundary temporal mirror correct.
- DateTime/Time + Quantity ('day','year','week','minute'); non-temporal unit
  ('mg') → null.
- Exp/Ln/Log: Ln(0)/Ln(neg)/Log(neg base)/Log(0 arg) → null; Ln of
  28-digit decimal fine; Exp(100) → null is spec-correct (result exceeds the
  CQL §2.3 Decimal range 10^28, overflow → null); Exp(-1000) → 0E-8.
- Divide Integer/Integer → Decimal (7/2 → 3.50000000; -7/2 → -3.50000000).
- Typed-guard interplay with conversions: Abs(ToInteger('-7')) → 7 (static
  inference intact), Abs(ToDecimal), Ceiling(ToDecimal), ToDecimal feeds
  Divide/Ln/HighBoundary — all exact scale-8 Decimals on both engines.
- End-to-end retrieve execution (probe4): arithmetic in where clauses over
  [Observation] retrieves with `as Quantity` comparisons (90.53 'mg' >
  90 'mg' + 0.4 'mg' → true) executes identically on both engines.

## Issues logged (evolution.json)

1. **QA-001 HIGH** — Quantity/Quantity Divide does not apply the unit
   conversion factor for commensurable units: 1000 'mg' / 1 'g' → 1000
   'mg/g' on both engines. Reference engine (DivideEvaluator.kt, cqframework
   main) uses `ucumService.divideBy`, which converts and cancels to 1.0 '1'.
   Both the numeric value and unit are wrong — silent wrong-value defect.
   Root: pint division in `fhir4ds/cql/duckdb/udf/quantity.py`
   `quantityDivide` never reduces units; native path mirrors it (dual-engine
   fix required in lockstep).
2. **QA-002 MEDIUM** — statically-known invalid operand mixtures silently
   translate to NULL: `1 + 1 'mg'`, `1 - 1 'mg'`, `10 / 2 'mg'`,
   `HighBoundary(5 'mg', 3)` → null. Reference throws
   InvalidOperatorArgument; the CQL-10 HISTORIAN typed-guard contract
   (uniform typed TranslationError for statically wrong operand types)
   covers String/Boolean but not Quantity operands or scalar-vs-Quantity
   mixtures for + - /.

## Spec verification

- cql.hl7.org 09-b-cqlreference: Divide/Add signatures + implicit conversion
  notes; High/LowBoundary signatures (Decimal/Date/DateTime/Time only, no
  Quantity overload; precision > max → null).
- cqframework/clinical_quality_language main: DivideEvaluator.kt,
  AddEvaluator.kt, HighBoundaryEvaluator.kt, LowBoundaryEvaluator.kt
  (fetched raw; quantity divide path quoted in evolution.json QA-001).
- Official fixtures: CqlArithmeticFunctionsTest.xml Divide1Q1Q (unit '1'),
  TruncatedDivide quantity group (unit preserved).

Baseline conformance run deferred to FIX-phase recovery gate per campaign
convention.
