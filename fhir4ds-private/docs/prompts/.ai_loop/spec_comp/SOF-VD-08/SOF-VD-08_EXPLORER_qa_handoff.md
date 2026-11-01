# QA Handoff — SOF-VD-08 EXPLORER (combined battery)

## Verdict: CLEAN — 12-case combined battery PARITY OK (E half)

E1 forEachOrNull enclosing + unionAll branch (null-row suppression scope);
E2 repeat arm + forEach arm with DIFFERENT names -> ValidationError (arms must
share names+types — schema match rule); E3 typed arms match (6 rows incl.
('p3','p3') id-arm row); E4 typed arms mismatch -> ValidationError; E5 deep
nested unionAll (3 levels, bare-branch shape; 5 rows); E6 select-level where
filters ALL branch rows.

Evidence: .temp/qa/speccomp2/sofvd08_historian_explorer_probe1.py
