# QA Handoff - CQL-19 EXPLORER

Personality: EXPLORER
Chunk: CQL-19, List Operators Part 2

Probe focus:
- Query-produced scalar lists feeding `Last`, `Length`, `Tail`, `Skip`, `Take`, list union, proper inclusion, and `singleton from`.
- Definition aliases over scalar query-produced lists.
- Regression coverage for CQL-19 SKEPTIC/HISTORIAN fixes: typed-null list length, Integer-only `Skip`/`Take` counts, interval semantic list equality.
- Forced Python fallback, native-loaded registration, and no-Python/browser-style C++ registration.

Finding:
- `QA-001` HIGH: scalar query-produced lists were translated as scalar subqueries for Part 2 list operators. Reproducers such as `Length((from {1,2,3} X return X))`, `(from {1,2,3} X return X) properly includes 2`, and `Length((from {1,2} X return X) union {2,3})` produced DuckDB binder errors or scalar truncation instead of CQL list behavior. `singleton from (from {1,2} X return X)` also failed to use strict list cardinality semantics.

Fresh probe:
- `.temp/qa/cql19_explorer_probe.py`
