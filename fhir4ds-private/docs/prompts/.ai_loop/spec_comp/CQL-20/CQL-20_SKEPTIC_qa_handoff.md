# QA Handoff — CQL-20 SKEPTIC (aggregate functions)

## Verdict: CLEAN — 20/20 fresh dual-path cases, 0 parity diffs

Sum/Avg scale-8 Decimal exact; Min/Max ints+decimals; Count null-skip (2 of 3);
Median even (2.5) / odd (2); StdDev sample 2.13808994 / Variance 4.57142857 /
PopulationStdDev 2.0 (n-1 vs n denominators verified); GeometricMean({1,3,9,27,81})
= 9.000000000000002 (transcendental floating-point, bounds-checked, BOTH engines
byte-identical); AllTrue/AnyTrue truth rows; Product 24; Mode({1,2,2,3}) = 2;
Sum({null,null}) = null (empty-after-null-filter doctrine). 4 probe-expectation
form fixes (Decimal-vs-string compare) — no engine defects.

Evidence: .temp/qa/speccomp2/cql20_skeptic_probe1.py (flagged=0)
