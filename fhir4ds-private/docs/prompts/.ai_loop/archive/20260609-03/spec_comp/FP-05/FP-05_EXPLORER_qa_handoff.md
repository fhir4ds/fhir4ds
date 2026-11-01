# QA Handoff - FP-05 EXPLORER

Personality: EXPLORER
Scope: FHIRPath Normative Release Section 5.3 Subsetting and Section 5.4 Combining.

Spec grounding:
- Section 4.4.1 says a single-input function passed an empty collection as an argument returns an empty collection unless a later section overrides it.
- Section 5.3.6 defines `skip(num : Integer)` and Section 5.3.7 defines `take(num : Integer)`.
- Section 5.4 defines `union(other)` as equality-based duplicate elimination and `combine(other)` as merge without duplicate elimination.

Probe:
- Created `.temp/qa/fp05_explorer_probe.py` with the workspace root pinned onto `sys.path`.
- Compared native-loaded DuckDB extension against forced Python fallback across 59 pathological/chained cases covering indexers, `single()`, `first()`, `last()`, `tail()`, `skip(num)`, `take(num)`, `intersect(other)`, `exclude(other)`, `union(other)`, `combine(other)`, duplicate/order behavior, equality-backed set semantics, invalid arity, `$index`, and nested `select()` contexts.

Finding:
- `QA-001` MEDIUM: forced Python fallback marks `a.skip({})` and `a.take({})` invalid in `fhirpath_is_valid()` even though public result UDFs return empty/NULL and native C++ treats the expressions as valid. The fallback sends the empty argument list to `int()` inside `skip_fn`/`take_fn`, producing a TypeError that validation reports as false.

Validation at QA:
- Probe result: 59 cases, 2 native/fallback mismatches, 0 expectation failures.
