# QA Handoff - CQL-18 EXPLORER

## Scope

- Chunk: CQL-18, List Operators Part 1.
- Personality: EXPLORER.
- Surfaces tested freshly: forced Python fallback, native-loaded DuckDB registration, and no-Python/browser-style C++ runtime via pure SQL macros.
- Spec source: CQL Reference v1.5.3 Appendix B, List Operators.

## Fresh Probes

- Direct list helper SQL over all three surfaces:
  - `CQLListElementEqual` and `CQLListContainsEq` with large mixed Long/Decimal operands.
  - null-aware equality/equivalence, except/intersect, and chained `First(CQLListIntersectEq(...))`.
- Translated CQL over all three surfaces:
  - large mixed numeric `in` / list equality.
  - chained `First(({ null, 1, 2 } intersect { null, 2 }) except { null })`.
  - nested Quantity `except` + `intersect` + `distinct`.
  - `flatten` plus null equality and whitespace-normalized list equivalence.

## Findings

### QA-001 - OPEN - MEDIUM

Mixed numeric list element equality rounds large exact numeric values through `DOUBLE`.

Evidence:

```sql
SELECT CQLListElementEqual(
  9223372036854775807::BIGINT,
  9223372036854775806::DECIMAL(19,0)
);
```

Actual on forced Python fallback, native-loaded registration, and no-Python/browser-style C++: `TRUE`.

Expected: `FALSE`; the operands are distinct exact numeric values. The same false positive appears in `CQLListContainsEq([9223372036854775807::BIGINT], 9223372036854775806::DECIMAL(19,0))`.

Root-cause hypothesis: `CQLListElementEqual` casts mixed numeric operands to `DOUBLE`, which cannot distinguish adjacent integers above 2^53.

## Non-Findings

- Chained null/set behavior and Quantity set operations matched across all three surfaces in the fresh probe.
- Named-definition behavior was not treated as proof from prior runs; current tests were inspected only to avoid duplicate coverage.
