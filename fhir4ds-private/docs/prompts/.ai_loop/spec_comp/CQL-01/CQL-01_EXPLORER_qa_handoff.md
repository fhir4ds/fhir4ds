# QA Handoff — CQL-01 EXPLORER

## Verdict: CLEAN — 27/27 fresh fuzz cases, 0 diffs (seed 20261002)

Extreme magnitudes (int32^2 overflow, Long*2 overflow, 28-digit decimals, 1e-8
sums); 8-term arithmetic chains; div/mod towers; string concat towers; boolean
logic precedence; chained comparisons; mixed-type seeded random pairs
(int/decimal/long/string/bool x 8 operators) — all symmetric native vs fallback
(errors raise identically on both).

Evidence: .temp/qa/speccomp2/cql01_explorer_probe1.py
