# QA Handoff — CQL-01 SKEPTIC (CQL 1.5 primitive types)

## Verdict: CLEAN — 26/26 fresh dual-path cases, 0 diffs

Boolean literals/and/not; Integer int32 bounds (max ok, 2147483648 ValueError BOTH);
Integer add; exact-Decimal division 7/2 -> Decimal('3.50000000'); Long bounds
(9223372036854775807L ok, overflow ValueError BOTH); Long arithmetic; Decimal
exactness (0.1+0.2 = Decimal('0.3'); 0.1+0.2=0.3 TRUE); trailing-zero equality;
scale-8 rendering; String concat/escapes/equality/case-sensitivity; Integer->Decimal
implicit promotion (1 + 1.5 = Decimal('2.5')); Boolean-in-arith invalid BOTH raise;
Truncate->Integer; div/mod incl. negative operand sign.

Evidence: .temp/qa/speccomp2/cql01_skeptic_probe1.py
