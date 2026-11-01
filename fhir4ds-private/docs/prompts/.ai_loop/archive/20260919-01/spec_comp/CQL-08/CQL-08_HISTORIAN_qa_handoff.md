# QA Handoff — CQL-08 HISTORIAN (iteration 1, 2026-08-20)

Chunk: CQL 1.5 Nullological Operators (Coalesce, IsNull, IsTrue, IsFalse).
Spec verified live this launch: cql.hl7.org 09-b Appendix B — ToInteger
signatures, Table 9-E conversion matrix (three targeted fetches), plus the
official CqlNullologicalOperatorsTest.xml fixtures (Coalesce scalar/list/
DateTime/Time, IsNull) re-read directly from
fhir4ds/cql/tests/official/cql-tests/tests/cql/.

## Probe strategy (HISTORIAN: institutional memory + NEW divergences)
- probe1.out: SQL-surface matrix, 21 cases x py/cpp (variadic 7-arg, nested
  Coalesce, Boolean coalescing, list-literal boundary errors, arithmetic
  composition).
- probe2.out: CQL-translator-level matrix, 17 cases x py/cpp — fixture-shaped
  list overloads (Coalesce({'a'},null,null) -> ['a'] matches official
  fixture), typed-null mixes, Date/DateTime and Quantity coalescing, static
  type-family guard both orders, nested-Coalesce escape hatch.
- Triage of the 3 SKEPTIC-documented pre-existing working-tree test failures.

## Verified clean (py == cpp everywhere)
- SKEPTIC's 2 fixes re-verified: 7-arg Coalesce works; static String/numeric
  mix raises uniform TranslationError in both orders.
- List-overload Coalesce passthrough matches official fixtures exactly.
- Decimal/Integer Coalesce mixing promotes to Decimal (spec Table 9-E
  implicit Integer->Decimal) -> 2.5 preserved, both paths.
- Date/DateTime/Time/Quantity Coalesce, nested Coalesce(null,null) chains,
  IsNull(Coalesce(null,null))=true, IsTrue(all-null)=false.

## Issues logged
- QA-001 MEDIUM OPEN — ToInteger/ToLong accept Decimal via truncation and
  ConvertsToInteger(1.5)=True on BOTH paths. CQL 1.5 Table 9-E defines NO
  Decimal->Integer/Long conversion and ToInteger overloads are
  Boolean/String/Long only (verified live x2). This is the CQL-07 master
  working-tree truncation branch; campaign tests (CQL-01) correctly expect
  False/None. No official fixture pins truncation.
- QA-002 MEDIUM OPEN — Coalesce(1, Coalesce(null,'a')) escapes the SKEPTIC
  static type-family guard (nested call static type not propagated) and leaks
  a raw DuckDB Binder Error at execution instead of a typed TranslationError.
- QA-003 LOW OPEN — stale test pin: structural parity QuantityToString
  expects "38 'weeks'" but both engines correctly produce "38 weeks" per the
  newer CQL-06 calendar-keyword macro fix ('cm' stays quoted). Test-only fix.
- QA-004 LOW INTENDED — re-confirmation of SKEPTIC's INTENDED pins; no code
  change.

Probes: .temp/qa/cql08_historian_2026_08_20/ (probe1.out, probe2.out).
