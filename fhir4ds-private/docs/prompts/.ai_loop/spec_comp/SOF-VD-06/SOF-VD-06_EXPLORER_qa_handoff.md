# QA Handoff — SOF-VD-06 EXPLORER (combined battery)

## Verdict: CLEAN — 12-case combined battery PARITY OK (E half)

E1 exists()-gated forEach (iif(name.exists(), name, {})); E2 iif-branch
iteration target; E3 empty-literal {} forEach -> 0 rows; E4 nested forEach
stack (contact → given; mid-column re-focused NULL per doctrine); E5
%context vs %resource distinct; E6 typed string in forEach.

Evidence: .temp/qa/speccomp2/sofvd06_historian_explorer_probe1.py
