# QA Handoff — CQL-10 HISTORIAN (arithmetic spec rows)

## Verdict: CLEAN — H-rows parity-OK, 0 diffs

Spec rows: 2+3=5; 2.5+3.5=Decimal('6.0'); 10/4=Decimal('2.50000000');
10 div 3=3; 10 mod 3=1; 2.2 div 1.8=Decimal('1') (truncation per CQL-10
doctrine/fixture); 5L+6L=11; 2147483647+1=NULL (int32 overflow).

Evidence: .temp/qa/speccomp2/cql10_historian_explorer_probe1.py (H rows)
