# QA Handoff — CQL-11 SKEPTIC (arithmetic functions Part 2)

## Verdict: CLEAN — 5/6 libs parity-OK w/ correct values; 1 EXC adjudicated (spelling)

Max/Min (list + two-arg + nulls-ignored + Quantity element-in-own-unit: Max({1 'g',
500 'mg'})=1 'g', Min({1 'g',1500 'mg'})=1 'g'); Round half-away incl. negative tie
(-0.5 -> -1.00000000) + precision form; Truncate toward-zero Integer; successor/
predecessor over Integer and Date; Negate() is NOT CQL (unary minus only) — corrected
spellings all parity-OK (-5, -(5), Precision(1.587)=3 [scale after implementation
scale-8 rounding], Power(2,10)=1024, 2^10, 7 mod 3=1).

Evidence: .temp/qa/speccomp2/cql11_skeptic_probe1.py + /tmp/opencode/cql11_adj.py
