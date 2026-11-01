# QA Handoff — CQL-06 HISTORIAN

## Verdict: CLEAN — 8/8 case-groups, 0 diffs (normative walk)

Table 9-F boolean strings full set (TRUE/T/t/yes/Y/1/0/no/n/f/FALSE all True);
integer grammar ('0'/'-42'/'+42' True, '42 ' trailing-space False); long grammar
(max-int64 True, overflow False); decimal grammar ('1e3'/'.5'/'5.' False,
'-0.5' True); date grammar (partial '2024'/'2024-06' True, '2024-02-30' False,
dateTime-25:00 False); time grammar (bare '14'/'14:30' True, ':60' False);
quantity grammar (bare-calendar True, bare-UCUM False, double-quoted False);
ToString (5->'5', true->'true', 1.5->'1.5').

Evidence: .temp/qa/speccomp2/cql06_historian_probe1.py
