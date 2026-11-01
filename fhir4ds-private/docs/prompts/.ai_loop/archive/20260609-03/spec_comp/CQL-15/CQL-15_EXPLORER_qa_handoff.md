# QA Handoff - CQL-15 EXPLORER Retry

## Scope

- Personality: EXPLORER
- Chunk: CQL-15, Interval Operators Part 1
- Retry focus: Architect finding that valid `collapse ... per` still bypasses `per` semantics.

## Spec Anchor

CQL Reference v1.5.3 Appendix B says `collapse(argument, per)` uses `per` to partition the value-space and determine collapse precision. Numeric intervals require a Quantity with default unit `1`, and the value may be any valid positive decimal.

## Reproducer

- Direct expected path:
  - `expand([Interval[1,3], Interval[5,6]], per 2)` partitions to `[1,2]` and `[5,6]`.
  - `collapse_intervals(expand(...))` keeps `[1,2]` and `[5,6]`.
- Translated CQL:
  - `collapse { Interval[1, 3], Interval[5, 6] } per 2`
  - Actual SQL: `collapse_intervals(to_json([...]))`
  - Actual result: `[1,3]` and `[5,6]`

## Finding

`ARCH-001` is confirmed. Valid compatible `per` is ignored for translated collapse, so the translator returns a range not aligned to `per` partitions.

## Handoff

Fix translated `collapse ... per` by applying `per` before `collapse_intervals`, likely via the existing `expand(..., per)` partitioning helper. Preserve the incompatible-per NULL guard from iteration 1.
