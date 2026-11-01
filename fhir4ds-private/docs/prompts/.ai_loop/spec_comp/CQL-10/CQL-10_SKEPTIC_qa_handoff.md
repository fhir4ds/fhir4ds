# QA Handoff — CQL-10 SKEPTIC (arithmetic operators)

## Verdict: CLEAN — 3/3 libs parity-OK (15 defines), 0 diffs

arith-basic (2+3=5; 7-4=3; 6*7=42; 7/2=Decimal('3.50000000') scale-8;
7 div 2=3; 7 mod 3=1; 2^10=1024); arith-neg (-7 div 2=-3 truncation-toward-zero;
-7 mod 3=-1 dividend sign; -7/2=Decimal('-3.50000000'); (-2)^3=-8);
arith-null (1/0, 1 div 0, 1 mod 0 all NULL; Coalesce(1/0,42)=42.0).

Evidence: .temp/qa/speccomp2/cql10_skeptic_probe1.py
