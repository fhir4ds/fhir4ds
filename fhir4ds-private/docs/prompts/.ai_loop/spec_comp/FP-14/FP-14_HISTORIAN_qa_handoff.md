# QA Handoff — FP-14 HISTORIAN (§6.2)

## Verdict: CLEAN — 15/15 fresh cases; 1 MISS adjudicated (100 'cm' < 2 'm' -> true; my fixture math)

Spec-verbatim rows: tz -04:00 vs -05:00 same-local true; @T10:30:00.0>@T10:30:00 false (combined precision);
cross-type/date-vs-time/empty rows.

Evidence: .temp/qa/speccomp2/fp14_historian_probe1.py
