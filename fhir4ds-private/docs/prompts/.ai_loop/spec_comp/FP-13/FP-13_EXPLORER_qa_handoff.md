# QA Handoff — FP-13 EXPLORER (§6.1 Equality family)

## Verdict: CLEAN — 31/31 fresh fuzz cases, 0 parity diffs

Equality/equivalence chains (eq→eq→bool, not/neq, eq implies, iif-over-eq,
where-over-eq, union-collapse); pathological operands (unicode café≠cafe, ß~SS
case-fold, emoji, null-literal, empty-in-chain, quantity conjunctions, 28-digit
decimal identity, tz/date chains, double negation); error containment
(iif dead-branch 1='x'); empty variants; 10 seeded random atom-pair×op
compositions (seed 20261002). All symmetric native+fallback.

Evidence: .temp/qa/speccomp2/fp13_explorer_probe1.py
