# QA Handoff: CQL-13 SKEPTIC

Scope: CQL Date/Time Operators Part 1: Date/DateTime construction, precision-aware before/after, component extraction, DateTime plus Quantity, and difference/duration between.

Spec checked: current CQL Reference v1.5.3 Appendix B Date and Time Operators. The key normative distinction is that `duration between` returns whole calendar periods, while `difference between` returns crossed boundaries. The reference example states `months between @2012-01-02 and @2012` evaluates to uncertainty interval `[0, 10]`.

Hypotheses attacked:
- Direct helpers might accept invalid timezone offsets such as `+14:01`.
- Runtime Date/DateTime constructors might coerce non-integer dynamic components.
- DateTime quantity arithmetic might lose input precision.
- Component extraction might read missing partial-precision fields as zeros.
- Duration and difference uncertainty might accidentally share one boundary algorithm.

Finding:
- `QA-001` HIGH `SPEC_VIOLATION`: `cqlDurationBetween('2012-01-02', '2012', 'month')` returned `{"start":0,"end":11,...}` across forced Python fallback, native-loaded registration, and no-Python C++ runtime. The corresponding `cqlDifferenceBetween` result of `[0, 11]` is correct, but duration should be `[0, 10]`.

Fresh probe:
- `.temp/qa/cql13_skeptic_probe.py`
