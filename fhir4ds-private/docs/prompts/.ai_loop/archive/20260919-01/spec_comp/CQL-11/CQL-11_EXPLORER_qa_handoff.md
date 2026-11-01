# QA Handoff — CQL-11 EXPLORER (2026-08-21)

Personality: EXPLORER. Chunk CQL-11 Arithmetic Operators Part 2.

## Probed (dual-engine: native cpp + Python fallback, translation + DuckDB execution)
- Successor/predecessor chains at type max/min for Integer, Long, Decimal, DateTime, Time (runtime, non-static-folded via Coalesce({...}))
- Predecessor/successor at every temporal precision (year/month/day/hour/min/sec/ms) incl. timezone-offset literals; lexical precision preserved
- Precision overloads: Decimal, Date, DateTime w/ offset, Time (@T10:30 → 4 per spec), Quantity
- Round: negative precision (123,-2)→100, (125,-1)→130, ties ±0.5 away from zero — all correct
- Modulo matrix incl. negative divisors/operands, Decimal mods, mod 0 → null
- TruncatedDivide sign matrix, Long min-near, mixed Long/Decimal — correct truncate-toward-zero
- Power fractional/negative exponents of Integer bases, unrepresentable → null
- Negate on Quantity, quantity products, and temporal-derived (duration between)
- Min/Max Quantity cross-unit (convertible preserved left-unit, non-convertible → null; per CQL-03 doctrine)
- Retrieve where-clauses with from [Observation] alias + `as Decimal` guard and direct dynamic div/Power/Truncate/Round (fhirpath_number guard fires through alias indirection); end-to-end DuckDB execution both engines
- Partial Time literals require @ prefix (bare T05:30 correctly not Time literal)

## Verified against spec
CQL 1.5 Appendix B (Arithmetic Operators intro, Successor, Predecessor, Negate, Round, Modulo, TruncatedDivide, Precision) — fetched full reference text.

## Issues logged
- QA-001 HIGH: Integer successor/predecessor boundary returns out-of-range value (2147483648) instead of null for statically-Integer non-literal operands, both engines.
- QA-002 HIGH: `-(days between ...)` binder error -(VARCHAR); duration-between lowers to VARCHAR-returning cqlDurationBetween and unary Negate lacks normalization.
- QA-003 MEDIUM: `-(3 days)` unit divergence: Python fallback 'day' vs native 'd' (pint round-trip normalizes).
- QA-004 LOW: parse_expression silently ignores trailing tokens.

Probes: /mnt/d/fhir4ds/.temp/qa/probe1.log, probe2.log, probe3.log, probe3.sql
