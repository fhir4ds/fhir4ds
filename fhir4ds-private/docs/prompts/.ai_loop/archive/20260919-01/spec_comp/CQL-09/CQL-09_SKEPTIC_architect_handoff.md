# Architect Handoff — CQL-09 Comparison Operators (iteration 1)

## Summary
QA (SKEPTIC) probed the full CQL 1.5 §9 comparison-operator surface — null propagation, precision-walking temporals, exact-Decimal numerics, unit-aware quantities, Between bounds, Code/Concept = and ~, list/tuple/interval/ratio equality, and e2e retrieve where-clauses — on both forced-Python and native paths with zero parity divergence. Two genuine MEDIUM spec violations found and fixed: (QA-001) list equality erased uncertainty for one-sided null elements (`{1,null} = {1,2}` → false instead of null), fixed in `CQLListEqualEq`/`CQLListEqualTemporalEq` with an inline null CASE that leaves `in`/`contains`/`except`/`distinct` semantics untouched; (QA-002) interval equality treated one-sided null bounds as unbounded/definitely-unequal, fixed dual-engine (Python `_interval_bound_equals_nullable`, native `Interval::equals_nullable`) to distinguish CLOSED null bounds (unknown → null) from OPEN null bounds (unbounded → false, preserving the pinned unbounded-interval doctrine). Native extension rebuilt and deployed (md5 fa873077f0573cc9cbd003247dab916e) across repo bundle and site-packages; verified via fresh no-Python LOAD. QA-003 (LOW) documents a CQL 1.5 spec-example erratum (`ListNotEqualIsNull`, `DateTimeWithMillisecondsEqualIsNull` contradict the algorithm text); terminal UNCONFIRMED, no fix.

## Issue counts
SPEC_VIOLATION: 2 (both VERIFIED). SPEC_AMBIGUITY: 1 (UNCONFIRMED, terminal). Architecture drift: 0. QA veto: not triggered.

## Validation evidence
New regression test `test_cql_null_uncertainty_preserved_in_list_and_interval_equality` (9 cases × 2 backends); focused comparison/list/interval parity suites 123/123 passed; full conformance gate 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — baseline held.

## Recommended fix order
None — no open CRITICAL/HIGH/MEDIUM issues remain. Clean exit at min_iterations=1.
