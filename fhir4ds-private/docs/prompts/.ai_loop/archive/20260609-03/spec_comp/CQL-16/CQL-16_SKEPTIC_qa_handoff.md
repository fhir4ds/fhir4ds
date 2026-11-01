# QA Handoff: CQL-16 SKEPTIC

Scope: CQL Interval Operators Part 2, focused on included-in precision, interval intersect, meets/meets-before/meets-after, interval equality/equivalence negation, on-or-before/on-or-after, overlaps/overlaps-before/overlaps-after, partial temporal precision, and Quantity dimension mismatch behavior.

Spec checked: CQL Reference v1.5.3 Appendix B interval operators. Relevant rules: `intersect` returns null when intervals do not overlap; interval relationships use semantic `Start`/`End`; `overlaps before` and `overlaps after` are defined in terms of `overlaps` plus ordering, so an unknown base overlap must remain unknown; temporal precision and incompatible Quantity comparisons can yield null.

Fresh probe: `.temp/qa/cql16_skeptic_probe.py`.

Findings:
- `QA-001` HIGH: `Interval[1, 5) intersect Interval[5, 7]` returns point interval `[5, 5]` on forced Python fallback and native-loaded registration. Expected SQL NULL because the shared endpoint is excluded by the left interval.
- `QA-002` HIGH: `intervalOverlapsBefore` / `intervalOverlapsAfter` convert unknown `intervalOverlaps` results to false. Reproduced with partial temporal precision and incompatible Quantity dimensions across Python/native and no-Python C++ where applicable.

Sanity controls passed in the probe:
- Closed touching intervals still intersect to `[5, 5]`.
- Hour-precision time intervals such as `Interval[@T03, @T04] meets Interval[@T05, @T06]` remain true.
- Existing translated partial-year overlap expressions that statically fold to null still behave as expected.
