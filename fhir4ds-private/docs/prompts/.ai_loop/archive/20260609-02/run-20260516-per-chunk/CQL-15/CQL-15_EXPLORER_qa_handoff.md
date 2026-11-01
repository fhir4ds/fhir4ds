# QA Handoff - CQL-15 EXPLORER

## Scope

Executed EXPLORER abuse for CQL Interval Operators Part 1 from current source without inspecting archived `spec_comp/**` outputs. Probed nested interval expressions, dynamic interval-valued CTEs, open/closed and missing boundaries, Date/DateTime/Time/numeric/Quantity point types, precision uncertainty, `collapse`/`expand` with `per`, `except` split/null behavior, translated scalar execution, native-loaded registration, forced Python fallback, and no-Python C++ helper coverage.

## Spec Anchors

- CQL 1.5.3 Appendix B Interval Operators: `after`, `before`, `contains`, `includes`, equality/equivalence, and `except` use Start/End interval boundary semantics.
- CQL 1.5.3 Appendix B `except`: returns null when the result would be a split/improper interval.
- CQL 1.5.3 Appendix B `expand`: `per` partitions by compatible point type units; Quantity intervals apply Quantity arithmetic/comparison semantics.
- CQL 1.5.3 Appendix B Comparison Operators: Quantity comparisons require same dimensions and use unit conversion where supported.

## Findings

1. `QA-CQL15-EXPLORER-001` - HIGH, verified after remediation.
   `Interval[1 'g', 2 'g'] contains 1500 'mg'` returned false across forced Python fallback, native-loaded registration, and no-Python C++ direct helper execution. Root cause was Quantity interval bounds/points being reduced to bare numeric values before comparison.

2. `QA-CQL15-EXPLORER-002` - MEDIUM, verified after remediation.
   `(Interval[1, 10] except Interval[1, 4]) contains 5` translated to generic DuckDB `system.contains(VARCHAR, INTEGER)` and binder-failed instead of routing the interval-valued `except` result through `intervalContains`.

## Reproducers

Primary probe: `.temp/qa/cql15_explorer_probe.py`

Key before-fix failures:

```sql
SELECT intervalContains(
  intervalFromBounds('{"value":1,"unit":"g","code":"g"}',
                     '{"value":2,"unit":"g","code":"g"}', true, true),
  '{"value":1500,"unit":"mg","code":"mg"}'
);
```

```cql
define NestedContains:
  (Interval[1, 10] except Interval[1, 4]) contains 5
```

## Post-Fix QA Result

The probe passes the fixed cases across forced Python fallback, native-loaded registration, and no-Python C++ direct helper execution. Remaining checked behaviors, including split `except` returning NULL, open DateTime semantic equality, partial precision uncertainty, `collapse`, `expand`, and dynamic CTE interval composition, matched expected behavior.
