# QA Handoff - CQL-16 EXPLORER

Scope: CQL Interval Operators Part 2, fresh probes against current source after SKEPTIC/HISTORIAN edits. I used CQL 1.5.3 Appendix B for the normative interval and comparison rules, then compared forced Python fallback, native-loaded registration, and no-Python/browser-style C++.

Probe artifact: `.temp/qa/cql16_explorer_probe.py`.

Findings:

- `QA-001` MEDIUM: interval `on or after` / `on or before` over partial Date intervals returns definite booleans instead of SQL NULL. Repro: `intervalOnOrAfter(intervalFromBounds('2014','2014',true,true), intervalFromBounds('2014-06-01','2014-06-02',true,true))` returned false on all three surfaces; the relation is uncertain.
- `QA-002` MEDIUM: Python fallback/native-loaded interval JSON double-encodes Quantity bounds for `intervalFromBounds` and `intervalIntersect`, while no-Python C++ emits nested Quantity objects.
- `QA-003` MEDIUM: incompatible Quantity interval `overlaps` raises in Python/native and returns false in no-Python C++; CQL Quantity comparison semantics require NULL for incompatible dimensions.

Sanity checks in the same probe passed for open-bound effective equality, temporal meets, partial-precision included/overlaps, nested intersect-then-included, and interval `!=`/`!~` over effective-equivalent open bounds.
