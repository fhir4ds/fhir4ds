# QA Handoff - CQL-19 HISTORIAN

## Scope

Spec chunk: CQL-19, List Operators Part 2. Personality: HISTORIAN.

Operators walked from current source, official CQL v1.5.3 Appendix B, and local official `CqlListOperatorsTest.xml`: `Last`, `Length`, list `!=`, list `!~`, `properly includes`, `properly included in`, `singleton from`, `Skip`, `Tail`, `Take`, and list `union`.

## Fresh Probe Summary

I compared translated SQL across forced Python fallback, native-loaded registration, and no-Python/browser-style C++ for current code. I did not inspect archived prior workflow outputs as proof.

Findings logged in `evolution.json`:

- `QA-001` MEDIUM: translated `singleton from` over runtime list expressions returned NULL for multi-item lists instead of throwing the spec-required runtime error.
- `QA-002` MEDIUM: query-form `take` lowered to raw `LIST_SLICE`, so null and negative counts did not match CQL `Take` semantics.
- `QA-003` MEDIUM: `Length(...)` did not recognize `Skip`/`Take`/`Tail` list-returning expressions, so null-list chains returned NULL instead of 0.

## Evidence

Fresh reproducer expressions before remediation:

```cql
define TakeNullQuery: {1,2,3} take (null as Integer)
define TakeNegativeQuery: {1,2,3} take -1
define SingletonSkipMulti: singleton from Skip({1,2,3},0)
define LengthSkipNull: Length(Skip(null as List<Integer>, 1))
define LengthTakeNull: Length(Take(null as List<Integer>, 1))
```

Observed before remediation: `(NULL)`, `[1,2,3]`, `(NULL)`, `(NULL)`, `(NULL)` respectively on all three DuckDB surfaces.
