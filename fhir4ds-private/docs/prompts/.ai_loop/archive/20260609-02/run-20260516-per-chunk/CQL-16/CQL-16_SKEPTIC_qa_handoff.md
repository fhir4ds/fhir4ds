# QA Handoff: CQL-16 SKEPTIC

Scope: CQL Interval Operators Part 2, using current source/spec/current tests only. Archive outputs were not used as evidence.

Spec basis: CQL v1.5.3 Appendix B interval operators. `included in`, `intersect`, `meets`, `not equal`, `not equivalent`, `same/on or after`, `same/on or before`, and `overlaps` all use interval Start/End semantics; `intersect` returns the overlapping portion; `meets` uses predecessor/successor and partial Date/DateTime/Time boundaries meet at their authored precision.

SKEPTIC hypotheses tested:
- Set operations may mishandle one-sided unbounded intervals.
- Browser/no-Python C++ may expose interval behavior hidden by native-loaded Python shadows.
- `meets` may confuse touching/overlapping closed boundaries with adjacency.
- `on or before`/`on or after` may compare authored bounds instead of effective Start/End.
- Partial precision Time/DateTime may use millisecond successor instead of boundary precision.

Fresh probes compared forced Python fallback, native-loaded registration, and no-Python/browser-style C++ where applicable. Findings logged in `evolution.json`:
- QA-001: `intervalIntersect` returns the wrong overlapping interval for one-sided unbounded intervals.
- QA-002: no-Python C++ reports closed overlapping intervals as `meets`.
- QA-003: no-Python C++ direct/translated `intervalOnOrAfter` and `intervalOnOrBefore` ignore effective open boundaries.
- QA-004: all paths fail CQL's partial-precision `meets` rule for Time/DateTime hour boundaries.

Suggested remediation: fix interval set-operation bound selection for unbounded intersections in Python and C++, route C++ meets/on-or-* through effective Start/End helpers, and make temporal predecessor/successor step by authored boundary precision for Date, DateTime, and Time.
