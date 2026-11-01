# QA Handoff — CQL-07 EXPLORER

## Verdict: CLEAN — 28/28 fresh fuzz cases, 0 diffs (seed 20261002)

Conversion chains (ToBoolean(ToString(5)), ToInteger(ToString(42)), ToString(ToDecimal),
ToDecimal(ToString(1.25)), ToTime(ToString(@T09:15:00)), ToString(ToQuantity('3 days')));
pathological inputs ('' empty strings, 22-digit integer string, concat-composed
decimals); if-then-else + Coalesce over conversions; typed-null propagation;
temporal boundaries ('0001-01-01', T23:59:59.999); negative + fractional
calendar quantities; 10 seeded random fn x atom compositions — all symmetric
(including error-class identity).

Evidence: .temp/qa/speccomp2/cql07_explorer_probe1.py
