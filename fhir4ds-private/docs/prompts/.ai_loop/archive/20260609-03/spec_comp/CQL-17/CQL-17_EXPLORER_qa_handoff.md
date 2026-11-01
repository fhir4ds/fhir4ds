# QA Handoff: CQL-17 EXPLORER

Scope: CQL Interval Operators Part 3, with EXPLORER emphasis on composed interval outputs, direct public helper surfaces, native-loaded versus forced Python fallback versus no-Python C++ parity, and the review-35 malformed `expand per` risk.

Spec basis: CQL Reference v1.5.3 Appendix B interval operators. For `expand`, a supplied `per` determines the interval partition Quantity; only null `per` is the defaulting path.

Probed:
- `point from` after `intersect` over open/closed intervals.
- Quantity `intervalUnion` feeding `intervalContains`.
- `expand` and `expand_points` with malformed non-null `per` Quantity JSON.
- `expand` after `intervalUnion` with malformed non-null `per`.
- SQL NULL `per` defaulting to ensure the valid default path remained distinct.

Finding:
- `QA-001` HIGH: malformed non-null `expand` / `expand_points` `per` values were treated as omitted/default and returned expanded intervals instead of SQL NULL across forced Python fallback, native-loaded, and no-Python C++ registrations.

Fresh probe:
- `.temp/qa/cql17_explorer_probe.py`
