# QA Handoff — CQL-09 Comparison Operators (SKEPTIC, iteration 1)

## Scope
CQL 1.5 §9 comparison operators: Between, Equal, Equivalent, Greater, GreaterOrEqual, Less, LessOrEqual, NotEqual, NotEquivalent. Verified against cql.hl7.org 09-b-cqlreference.html (fetched, quoted, cached at /tmp/cqlref.html). Probes at `/mnt/d/fhir4ds/.temp/qa/cql09/` (skeptic_probe1..3, probe4 e2e, probe5 spec-examples inline). Every case executed on BOTH forced-Python and native-loaded DuckDB registrations; zero native-vs-Python parity divergences observed.

## Coverage highlights (all conformant)
- Null propagation: `=`/`!=`/`<`..`>=` with any null operand → null (incl. `null != null`, `null !~ 5`→true, `null ~ null`→true). Equivalent never null.
- Temporals: precision-walk (`@2012-01-01 = @2012-01-01T12`→null, `~`→false), seconds+ms single decimal precision, unspecified ms = .0, timezone-instant normalization (`@2012-01-01T23:00:00.000-01:00 = @2012-01-02T00:00:00.000Z`→true).
- Strings: `=` case-sensitive code-point; `~` case-insensitive + whitespace-normalized (tabs/newlines/edges).
- Numerics: trailing zeros, `1.0 ~ 1.04`→true (least-precision rounding), Long/Integer/Decimal implicit casts, exact-Decimal `0.1+0.2 = 0.3`→true, Long boundaries.
- Quantities: unit-aware =/~/between across UCUM, dimension mismatch → null (for =,<,!=) and false (for ~,!~), calendar vs definite-time durations, negatives, list-of-quantity unit-aware equality, Ratio `1:8 ~ 2:16`→true.
- Between: inclusive, any-null → null, low>high → false, mixed numeric/quantity/string/temporal incl. mixed-precision null.
- Codes/Concepts: `~` code+system case-insensitive, display/version ignored, Concept non-empty intersection (per pinned CQL-02 doctrine); `=` display-inclusive with null display → null (pinned).
- e2e retrieve where-clauses: value > quantity, unit-aware between, date =, string ~, code ~ — correct on both paths.

## Issues
- QA-001 (MEDIUM, OPEN): `{1, null} = {1, 2}` → false, spec null. Root: `CQLListElementEqual` one-sided-null branch in macros/list.py. Shared by both paths.
- QA-002 (MEDIUM, OPEN): `Interval[null,3] = Interval[1,3]` / `Interval[1,3] = Interval[1,null]` → false, spec null. Roots: `_bounds_equal` (udf/interval.py) and `Interval::equals_nullable` (extensions/cql/src/cql/interval.cpp, 'unbounded' misreading of null bounds).
- QA-003 (LOW, UNCONFIRMED): spec's own examples ListNotEqualIsNull / DateTimeWithMillisecondsEqualIsNull contradict its algorithm text; implementation follows the algorithm. Spec erratum, no fix.

## False positives resolved (do NOT "fix")
- `0.1 + 0.2 = 0.3` → true is correct (exact Decimal arithmetic, spec).
- `5 'g' between 500 'mg' and 2000 'mg'` → false correct (5 g = 5000 mg > 2000 mg).
- `3.5 'cm2' !~ 3.5 'cm'` → true correct (spec example QuantityNotEquivalentIsTrue).
- `1 !~ '1'` → true correct (~ of type mismatch is false).
- Off-by-one-hour timezone equality → false correct.
