# QA Handoff — CQL-13 SKEPTIC (DateTime operators Part 1)

## Verdict: CLEAN — probe1 green (25 cases, 0 parity diffs) after 6 adjudications

Adjudications (all probe-expectation errors; both engines identical everywhere):
(1) Time+qty renders T-PREFIXED at input precision ('T12:00'); (2) after month of
SAME month = False; (3) before later-month = True; (4) DateTime(2024,6,15,10,30)
renders minute-precision; (5) Time(14,30) renders 'T14:30'; (6) @-LITERAL partial-precision
months-between TRUNCATES to 0 (both engines) — the uncertainty INTERVAL form is emitted
ONLY for DateTime() CONSTRUCTOR partial-precision operands, fixture-pinned at
CqlDateTimeOperatorsTest.xml:847-851 (months between DateTime(2005) and DateTime(2006,5)
→ Interval[4,16], engine-matched live).

Evidence: .temp/qa/speccomp2/cql13_skeptic_probe1.py
