# QA Handoff — CQL-08 EXPLORER

## Verdict: CLEAN — adversarial compositions from the same evidence base

Coalesce chains with null-feeding expressions (1/0, ToQuantity('junk'));
IsTrue/IsFalse over comparisons and conversions; nested Coalesce depth;
if-then-else over nullological results; resource-backed absent-field rows.
All identical native vs fallback; errors raise identically.

Evidence: .temp/qa/speccomp2/cql08_skeptic_probe1.py + /tmp/opencode/cql08_adj.py
