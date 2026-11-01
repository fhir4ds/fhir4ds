# QA Handoff — SOF-VD-07 HISTORIAN (combined battery)

## Verdict: CLEAN — 12-case combined battery PARITY OK (H half)

H1 where-filter on repeated nodes (startsWith); H2 root column beside repeat
(qid NULL at repeated focus — iterated-focus doctrine); H3 nested select under
repeat w/ typed integer item.count(); H4 multi-hop path item.item: start set =
depth-2 nodes, recursive follow of the SAME path yields nothing deeper (1.2's
item.item absent) -> [1.1, 1.2]; H5 overlapping paths [item, item.item] union
dedup; H6 typed collection under repeat (5 emitted nodes; kids lists).

Evidence: .temp/qa/speccomp2/sofvd07_historian_explorer_probe1.py
