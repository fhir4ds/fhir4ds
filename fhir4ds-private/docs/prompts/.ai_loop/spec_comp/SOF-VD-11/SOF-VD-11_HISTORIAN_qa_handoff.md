# QA Handoff — SOF-VD-11 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 12/12 cases, PARITY OK after 2 want fixes

H1 multi-name unroll (p1 Chalmers+Gray, p2 Gray); H2 nested name+address
stacks (city via %resource.address.first().city; None for p2); H3 Observation
component unroll (code.text at ITERATED focus -> systolic/diastolic; values
string-render); H4 typed collection (name.given flattened [John,Kim,Kim]);
H5 constant+where+forEach composition; H6 unionAll executed (arm rows).
E1 contained iteration (0 rows for plain patients); E2 nested select on
component coding; E3 EMPTY resources table -> 0 rows both engines; E4
all-null row for bare patient; E5 boolean typed render ('true'); E6
%rowIndex per-patient 0-based (p1:0,1; p2:0).

Adjudications: H3/E2 wants — code.text resolves at the iterated component
focus (NOT resource-level code); untyped numerics render as strings.

Evidence: .temp/qa/speccomp2/sofvd11_historian_explorer_probe1.py
