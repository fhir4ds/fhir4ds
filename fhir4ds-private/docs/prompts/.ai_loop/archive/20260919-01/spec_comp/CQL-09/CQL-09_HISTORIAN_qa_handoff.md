# QA Handoff — CQL-09 Comparison Operators (HISTORIAN, iteration 1)

## Scope
CQL 1.5 §9 comparison operators, HISTORIAN pass over the SKEPTIC-fixed tree.
Fresh probes at `/mnt/d/fhir4ds/.temp/qa/cql09/historian_probe{1,2}.py` plus a
tuple/interval-in-list spot probe (~75 cases), every case executed on BOTH
forced-Python and native-loaded registrations; zero native-vs-Python parity
divergences.

## New surfaces probed (beyond SKEPTIC)
- Uncertainty propagation through derived ops: `!=` / `!~` over uncertain
  list/interval equality; equivalent on lists with null elements; nested lists.
- Tuple equality: element-wise uncertainty, field order irrelevance, nested
  tuples, differing key sets, string equivalence inside tuples.
- Temporal ordered comparisons incl. Time type, coarse-vs-fine precision,
  seconds/ms combined precision.
- String lexical ordering (`<`/`<=`), between over strings/temporals/quantities.
- Quantity ordered comparisons across units and dimension mismatches.
- Code/Concept: null code on `=`, null-null `~`, order-sensitive Concept `=`
  vs intersection `~`, case-insensitive code+system `~`.
- Regression re-verification of SKEPTIC QA-001/QA-002 fixes: all intact
  (`{1,null}={1,2}`→null; interval closed-null→null, open-null→false).

## Issues
- QA-001 (MEDIUM, OPEN): nested list equality erases uncertainty —
  `{{1, null}, {2}} = {{1, 2}, {2}}` → false; spec null (§9.4 Equal: pairwise
  element equality recurses; `{1,null} = {1,2}` is uncertain). Root:
  `CQLListElementEqual` generic `left = right` fallback uses raw DuckDB list
  equality for LIST-typed elements. Both paths. DuckDB macros cannot recurse,
  so the fix must inline one nested level inside `CQLListEqualEq`/
  `CQLListEqualTemporalEq` and stay uncertainty-preserving at depth ≥3.
- QA-002 (MEDIUM, OPEN): tuple list elements erase uncertainty —
  `{ Tuple { a: 1, b: null } } = { Tuple { a: 1, b: 2 } }` → false; spec null.
  Root: tuple elements travel as `json_object`; `CQLListElementEqual` compares
  them with raw JSON equality (null field mismatch = definite inequality).
- QA-003 (LOW, INTENDED): `Code { code: null, system: 's' } =` same → true.
  §9.4 Equal does not define Code equality (only Equivalent covers codes);
  consistent with pinned CQL-02 absent==explicit-null doctrine. No fix.

## False positives resolved (conformant, do NOT "fix")
- `@2012-01-01T12:00 < @2012-01-01T12:00:00` → null (one side lacks seconds
  precision; §Greater: comparison stops, result null).
- `-1 'm' < 1 'cm'` → true (unit-aware: −100 cm < 1 cm).
- `{1,null} ~ {1,2}` → false (Equivalent never null), `!~` → true.
- Interval-in-list and quantity-in-list uncertainty already correct
  (`{Interval[null,3]} = {Interval[1,3]}` → null; `{1 'g'} = {1000 'mg'}` → true).
- Concept `=` order-sensitive false / `~` intersection true — correct.
