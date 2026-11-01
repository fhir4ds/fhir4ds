# QA Handoff — SOF-VD-08 HISTORIAN (combined battery)

## Verdict: CLEAN — 12-case combined battery PARITY OK (H half)

H1 three branches (9 rows, per-arm NULLs); H2 column reorder -> ParseError
(order matters); H3 forEach + where INSIDE branch; H4 %rowIndex resets per
branch (Chalmers 0/Gray 1 vs John 0/Kim 1); H5 empty forEach branch -> only
matching rows (p1 Cousin); H6 collection column in branch (per-patient lists).

Evidence: .temp/qa/speccomp2/sofvd08_historian_explorer_probe1.py
