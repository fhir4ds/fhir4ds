# QA Handoff: CQL-19 HISTORIAN

## Scope

- Chunk: CQL-19, List Operators Part 2.
- Personality: HISTORIAN.
- Spec source: CQL Reference v1.5.3 Appendix B, List Operators and Interval Operators.
- Focus: `Last`, `Length`, list `!=` / `!~`, `properly includes`, `properly included in`, `singleton from`, `Skip`, `Tail`, `Take`, and list `union`, with prior CQL-18/CQL-19 fixes in mind.

## Fresh Probe

- Probe file: `.temp/qa/cql19_historian_probe.py`.
- Backends checked: forced Python fallback, native-loaded DuckDB registration, and no-Python/native C++ surface.
- Adjacent CQL-19 SKEPTIC boundaries passed in the probe: typed-list `Length(null)` returned `0`, `Length(Tail(null as List<T>))` returned `0`, `Skip(..., null)` returned the source list, `Take(..., null)` returned `{}`, and static non-Integer `Skip`/`Take` counts were rejected.

## Finding

`QA-001` HIGH: List operators over interval-valued elements use raw transported interval JSON/string identity instead of CQL interval equality/equivalence semantics.

Evidence from the fresh probe:

- `{ Interval(1, 6] } = { Interval[2, 6] }` returned `false`; expected `true`.
- `{ Interval(1, 6] } != { Interval[2, 6] }` returned `true`; expected `false`.
- `{ Interval(1, 6], Interval[10, 11] } properly includes Interval[2, 6]` returned `false`; expected `true`.
- `Interval[2, 6] properly included in { Interval(1, 6], Interval[10, 11] }` returned `false`; expected `true`.
- `Length({ Interval(1, 6] } union { Interval[2, 6] })` returned `2`; expected `1`.
- Direct `CQLListElementEqual`, `CQLListElementEquivalent`, `CQLListContainsEq`, `CQLListEqualEq`, `CQLListEquivalentEq`, and `"Distinct"` showed the same mismatch across all three backend paths.

Spec basis:

- List `Equal`, `Distinct`, `Properly Includes`, `Properly Included In`, and `Union` all delegate element matching to equality semantics, with special handling only for null elements.
- Interval `Start` / `End` semantics define effective boundaries for open endpoints, and interval equality is expected to compare semantic interval values rather than raw authoring shape.

## Handoff

Proceed to FIX. The likely repair point is `fhir4ds/cql/duckdb/macros/list.py`: teach list element equality/equivalence helpers to detect interval-shaped JSON values and route them through `intervalEquals` / `intervalEquivalent`, preserving native Python fallback, native-loaded, and no-Python C++ parity. Add focused regression coverage to `test_list_part2_parity.py`.
