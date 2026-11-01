# QA Handoff - CQL-07 HISTORIAN

Personality: HISTORIAN
Chunk: CQL-07 - Type Operators / Conversions

Spec basis:
- CQL 1.5.3 Appendix B conversion table and conversion function definitions.
- `ConvertsToString` returns true when the argument can be converted to String.
- Quantity and Ratio have explicit String conversion support; invalid conversion inputs return null/false, not runtime/catalog errors.

Probe coverage:
- Fresh `.temp/qa/cql07_historian_probe.py` checks direct DuckDB conversion helper/UDF calls and translated CQL definitions on forced Python fallback and native-loaded registrations.
- Covered `ToBoolean`, `ToConcept`, `ToDate`, `ToDateTime`, `ToDecimal`, `ToLong`, `ToInteger`, `ToQuantity`, `ToRatio`, `ToString`, `ToTime`, and relevant `ConvertsTo*` predicates.
- Included prior-remediation boundaries: unsupported `ToString` structural/Concept values, invalid temporal strings, invalid Quantity/Ratio strings, Code/List<Code> to Concept, Quantity/Ratio string formatting, and native/fallback parity.

Finding:
- `QA-001` HIGH: translated conversion-check predicates over static Quantity/Ratio definition aliases could lower the alias as a missing resource CTE. Reproducer: `ConvertsToString(QuantityFromString)` where `QuantityFromString` is `ToQuantity('-0.1 ''mg''')` emitted `SELECT sub.resource FROM "QuantityFromString" ...` and raised a DuckDB catalog error instead of returning true.

Status:
- Issue reproduced and fixed during remediation.
