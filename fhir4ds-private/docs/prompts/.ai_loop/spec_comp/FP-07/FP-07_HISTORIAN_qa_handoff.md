# QA Handoff — FP-07 HISTORIAN (§5.5.4-§5.5.6 Date/DateTime/Decimal Conversion)

## Verdict: CLEAN — zero defects (22/22 fresh cases, 0 flags)

Normative-table walk: toDate partial-precision grammar + dateTime truncation +
date passthrough; convertsToDate calendar validity matrix; toDateTime T-marker
promotion (yearT/monthT/dateT), offset preservation, hour-range rejection;
toDecimal exact-Decimal rows, Boolean→1.0/0.0, Integer passthrough; convertsToDecimal
valid/junk; resource-backed birthDate round-trip equality anchor.

Evidence: .temp/qa/speccomp2/fp07_historian_probe1.py
