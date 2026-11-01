# QA Handoff — CQL-11 HISTORIAN (iteration 1, 2nd personality launch)

Personality: HISTORIAN (spec-walk). Chunk: CQL Arithmetic Operators Part 2
(Max/Min, Modulo, Multiply, Negate, Precision, Predecessor, Power, Round,
Subtract, Successor, Truncate, TruncatedDivide). All probes through
translate_cql + DuckDB execution on BOTH the Python-supplement and native
extension engines; spec text verified against cql.hl7.org Appendix B
(arithmetic + aggregate sections) and official cql-tests fixtures
(/mnt/d/cql-tests-runner/cql-tests CqlArithmeticFunctionsTest.xml).

Probe: /mnt/d/fhir4ds/.temp/qa/cql11_historian2_probe.py

## Verified clean (both engines)
- Predecessor/Successor on Integer/Long/Decimal numbers incl. min/max
  boundary nulls (predecessor of -2147483648, successor of Long max).
- Max/Min list aggregates: mixed Integer/Decimal/Long, empty list,
  all-null list, two-arg convenience form, boundary T limits.
- Power corners: 0^0=1, 0^-1=null, fractional negative exponent,
  invalid domain (math domain error handled -> null).
- Modulo decimal ties (5.5 mod 2.5, -5.5 mod 2.5), INT_MIN div -1 -> null
  (Long too) — SKEPTIC's cqlDivide fix holds at the extreme.
- Quantity: unit-mismatch subtract -> null (logged, not raised),
  g/mg TruncatedDivide, negate.
- Precision(null) -> null; Round(prec 8) exact.

## Issues opened
- QA-001 HIGH: Round/RoundTo macros use FLOOR, overridden in the same file
  by the CQL Floor macro (TRY_CAST AS INTEGER) -> RoundTo(123.456, 8) and
  Round(3147483647.05) return NULL instead of the rounded Decimal whenever
  the shifted value exceeds Integer range. Spec: only unrepresentable
  results are null. Shared macro => both engines affected; no C++ rebuild
  required (macro is Python-registered on both paths).
- QA-002 HIGH: Decimal literal Multiply overflow raises DuckDB
  OutOfRangeException instead of null (9999999999999999999999999999.0^2).
  Static overflow folding only covers Integer/Long; runtime Decimal
  operands also unguarded. Both engines.

## Reclassified INTENDED (spec-verified, NOT A BUG registry)
- Max(1, null) two-arg -> 1: two-arg Max/Min is a non-spec convenience
  (Appendix B defines list-only aggregates; list semantics ignore nulls).
- Min({1.0 'g', 500.0 'mg'}) -> 500.0 'mg': Min returns the minimum
  ELEMENT; comparison is unit-aware, element returned in its own unit.
- 2 'cm' * 3 'cm' -> 6 'cm2': spec Multiply explicitly defines UCUM unit
  multiplication (cm*cm -> cm2).
- Precision(0.000000001) -> 8: literal is unrepresentable at the
  implementation scale 8 (rounds to 0.00000000); Precision of the stored
  input = 8. Consistent with CQL-01 decimal-representability doctrine.
- 28-integer-digit decimal literal limit is spec (CQL §2.3, Decimal 28
  digits precision); 1E28-style scientific literals are not CQL grammar.
