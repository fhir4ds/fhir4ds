# QA Handoff — CQL-04 EXPLORER

## Verdict: CLEAN — 26/26 fuzz cases, 0 parity diffs (seed 20261002)

Logic towers with absorbing cells mid-chain (5-term and/or, implies chains, xor
chains); mixed precedence; not-towers over resource fields; resource×literal
compositions; if-then-else over logical results; null-side mixes (absent-field
comparisons with absorbing literals); 8 seeded random (operand×operator) pairs —
all symmetric native vs fallback (error rows raise identically).

Evidence: .temp/qa/speccomp2/cql04_explorer_probe1.py
