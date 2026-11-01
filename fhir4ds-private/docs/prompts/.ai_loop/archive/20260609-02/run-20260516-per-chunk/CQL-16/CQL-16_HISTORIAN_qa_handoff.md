# QA Handoff - CQL-16 HISTORIAN

Scope: CQL Interval Operators Part 2. I used current source, official CQL
Appendix B interval/equivalence/temporal precision semantics, current tests,
and fresh probes only. I compared forced Python fallback, native-loaded
DuckDB registration, and no-Python/browser-style C++ direct helper surfaces.

Findings:

- `QA-001` MEDIUM, verified: public no-Python C++ `intervalEquivalent` allowed
  SQL NULL propagation. `intervalEquivalent(NULL, NULL)` returned NULL instead
  of true, and one-null variants returned NULL instead of false.
- `QA-002` HIGH, verified: partial temporal precision uncertainty diverged.
  No-Python C++ parsed year-only interval bounds as numeric values in interval
  contexts, direct precision predicates returned false instead of NULL, and
  translated `overlaps day of` over static partial year intervals decomposed to
  raw string comparisons.

Fresh reproductions used:

```sql
SELECT intervalEquivalent(NULL, NULL);
SELECT intervalEquivalent(NULL, intervalFromBounds('1','2',true,true));
SELECT intervalOverlapsPrecise(intervalFromBounds('2014','2014',true,true), intervalFromBounds('2014-06-01','2014-06-02',true,true), 'day');
SELECT intervalContainsPrecise(intervalFromBounds('2014-06-01T00','2014-06-01T01',true,true), '2014-06-01T12', 'day');
```

```cql
define YearOverlapsDateDay: Interval[@2014, @2014] overlaps day of Interval[@2014-06-01, @2014-06-02]
define DateTimePointIncludedDay: @2014-06-01T12 included in day of Interval[@2014-06-01T00, @2014-06-01T01]
```

Post-remediation QA result: all repros match across Python fallback,
native-loaded registration, and no-Python C++. Focused interval/browser cluster
passed, official conformance returned 2822/2822, and full pytest returned
7200 passed / 5 skipped.
