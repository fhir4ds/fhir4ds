# QA Handoff — CQL-13 HISTORIAN

## Verdict: CLEAN — normative rows verified (part of the combined battery)

duration-vs-difference (years between 2020-06-15/2024-01-01=3 vs difference=4);
ctor uncertainty interval Interval[4,16] fixture-exact; Date+hour NULL; Time+day NULL;
month-end clamp Jan31+1mo=Feb29 (leap); Date(2024,null)='2024'; year-from component;
week precision NULL. Checker MISSes were string-vs-int/dict rendering forms only
(parity OK on every row).

Evidence: .temp/qa/speccomp2/cql13_historian_explorer_probe1.py (H rows)
