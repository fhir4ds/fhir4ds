# QA Handoff — FP-15 EXPLORER (§6.3)

## Verdict: CLEAN — 37/37 fresh fuzz cases, 0 parity diffs

is/as chains (is-then-as, as-then-is, double-as); is in where/select/iif (incl. nested
iif chains); spelling permutations (is()/as() forms, unqualified Quantity); System forms
(literals Integer/String/Decimal/Boolean; @date is DateTime; arithmetic/concat results);
unknown types; empty/multi-item propagation; root resource hierarchy checks (is Resource/
DomainResource); quantity .value typing; 8 seeded random atom×type compositions
(seed 20261002). All symmetric native vs fallback.

Evidence: .temp/qa/speccomp2/fp15_explorer_probe1.py
