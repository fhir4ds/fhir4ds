# QA Handoff - CQL-16 HISTORIAN

Scope: CQL Interval Operators Part 2, focused on Included In precision,
Intersect, Meets/Meets Before/Meets After, interval not equal/not equivalent,
On Or After/On Or Before precision, and Overlaps/Overlaps Before/Overlaps After.

Spec basis: CQL Reference 1.5.3 Appendix B interval operators. The reference
states that included-in and includes use semantic Start/End boundaries, interval
intersect returns the overlapping interval or null if there is no overlap,
meets uses predecessor/successor of effective boundaries, overlaps-before/after
requires overlap plus directional start/end comparison, precision comparisons
over partial temporal values may be null, and interval null arguments generally
return null for interval-interval overloads.

Fresh evidence produced in this accepted run:

- `.temp/qa/cql16_historian_probe.py` passed across forced Python fallback,
  native-loaded registration, and no-Python/browser-style C++ runtime.
- Probe cases covered official included-in day vs millisecond uncertainty,
  point-in-interval precision, half-open empty intersect, Quantity intersect
  with unit conversion, hour/month precision `meets`, effective open bounds for
  on-or-before/on-or-after, semantic interval equality/equivalence, partial
  temporal unknowns, and incompatible Quantity overlap unknowns.
- Focused interval parity/no-Python pytest passed: 27/27.
- Official CQL interval operator category passed: 412/412.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, overall 2822/2822.

Issues found: 0.

No source remediation is required for this HISTORIAN pass. The only probe
adjustment was environmental: the `.temp` probe inserts the workspace root into
`sys.path` so helper imports resolve to this checkout instead of an installed
package.
