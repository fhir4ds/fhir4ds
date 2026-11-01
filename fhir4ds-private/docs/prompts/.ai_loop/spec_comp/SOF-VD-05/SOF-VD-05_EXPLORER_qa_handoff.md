# QA Handoff — SOF-VD-05 EXPLORER (combined battery)

## Verdict: CLEAN — 12-case combined battery PARITY OK (E1-E6 half)

E1 %rowIndex in nested forEach: per-parent counter reset (p1 Chalmers=0/Gray=1,
p2 Gray=0). E2 unionAll nested: typed ParseError (schema mismatch — composition is
SOF-VD-08 scope). E3 collision at depth 3 → ParseError. E4 empty nested select in
forEach parent: rows still emitted per focus. E5 %resource.gender root-ref no-foreach.
E6 $this in forEach-over-path (contact.name.family) projection.

Evidence: .temp/qa/speccomp2/sofvd05_historian_explorer_probe1.py
