# QA Handoff: CQL-19 SKEPTIC

## Scope

CQL List Operators Part 2: `Last`, `Length`, list `!=`, list `!~`, list
`properly includes`, list `properly included in`, `singleton from`, `Skip`,
`Tail`, `Take`, and list `union`.

## Spec Source

Used current CQL Reference v1.5.3 Appendix B, List Operators:
https://cql.hl7.org/09-b-cqlreference.html

Relevant paraphrased requirements:
- `Skip(list, null)` returns the entire list; `Skip(list, negative)` returns an empty list.
- List `properly includes` / `properly included in` use CQL equality semantics, with null elements considered equal.
- `union` treats null list operands as empty lists and returns unique elements.
- `singleton from` returns the single element, returns null for null/empty lists, and throws a runtime error for lists with more than one element.

## Fresh Probe

Created and ran `.temp/qa/cql19_skeptic_probe.py` against:
- forced Python fallback registration
- native-loaded DuckDB registration
- no-Python/browser-style C++ runtime

## Findings

1. `QA-001` (`MEDIUM`): `Skip([1,3,5], NULL)` and `Skip([1,3,5], -1)` return SQL NULL on all three surfaces. Expected full list for null count and empty list for negative count.
2. `QA-002` (`MEDIUM`): translated list `properly includes` / `properly included in` still use DuckDB `list_contains` / `list_has_all`, so Quantity-equivalent elements such as `1 'g'` and `1000 'mg'` compare false.
3. `QA-003` (`MEDIUM`): translated `(null as List<Integer>) union (null as List<Integer>)` lowers to SQL NULL. Expected an empty list because both null operands are empty-list inputs for list union.
4. `QA-004` (`MEDIUM`): direct `SingletonFrom(['a','b'])` raises on forced Python fallback but returns SQL NULL on native-loaded and no-Python C++; expected a runtime error on all public DuckDB surfaces.

## State

`evolution.json` moved to `phase: FIX` with `QA-001` through `QA-004` open.
