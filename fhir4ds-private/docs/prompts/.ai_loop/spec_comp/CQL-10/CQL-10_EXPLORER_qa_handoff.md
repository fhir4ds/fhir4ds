# QA Handoff — CQL-10 EXPLORER (adversarial compositions)

## Verdict: CLEAN — E-rows parity-OK, 0 diffs

Precedence (1+2*3=7; (1+2)*3=9; 2*2^3=16); if-over-comparison 100;
Coalesce(10 div 0,7)=7; 5 'mg'+5 'mg' -> 10 mg Quantity JSON;
@2024-06-15+5 days=2024-06-20; -3.7+1.2=Decimal('-2.5').

Evidence: .temp/qa/speccomp2/cql10_historian_explorer_probe1.py (E rows)
