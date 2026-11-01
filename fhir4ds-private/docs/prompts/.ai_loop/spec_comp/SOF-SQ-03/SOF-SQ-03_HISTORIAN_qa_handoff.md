# QA Handoff — SOF-SQ-03 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 7/7 cases (flagged=0)

H1 three-level chain (Q->SV1->SV2->VD); H2 deep failure surfaces the
INNERMOST label ('base') + canonical ('http://vd'); H3 ambiguous dict
(resourceType Library + select keys) -> typed 'ambiguous' rejection; E1
unicode label rejected (sql-name ASCII); E2 sequential queries on one
shared connection; E3 SQLView raw body executes own SQL (parameter 0..0);
E4 main body referencing materialized view + :param together.

Evidence: .temp/qa/speccomp2/sofsq03_historian_explorer_probe1.py
