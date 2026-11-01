# QA Handoff — SOF-VD-06 HISTORIAN (combined battery)

## Verdict: CLEAN — 12-case combined battery PARITY OK (H half)

H1 where-in-foreach-select (array form); H2 forEach over filtered expr
(maiden); H3 primitive iteration + %rowIndex (John 0/Kim 1); H4 forEachOrNull
present collection like forEach + p3 null row; H5 root where (active = true)
+ forEach; H6 typed boolean column renders 'true'/'false' strings.

Evidence: .temp/qa/speccomp2/sofvd06_historian_explorer_probe1.py
