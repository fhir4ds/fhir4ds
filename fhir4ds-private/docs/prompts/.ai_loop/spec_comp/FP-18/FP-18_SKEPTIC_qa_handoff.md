# QA Handoff — FP-18 SKEPTIC (§6.6/§6.7 Arithmetic)

## Verdict: CLEAN — zero defects (40 fresh dual-path cases; 1 MISS adjudicated)

Adjudication: `-7 div 2.0` → ['-3'] — div truncates toward zero EVEN WITH Decimal
operands (fixture testDiv4 pins `2.2 div 1.8 = 1`); my -3.5 expectation was wrong.

Verified: spec-verbatim + - * / div mod rows + mod sign family; exact-Decimal
0.1+0.2=0.3; int32-overflow→Decimal; 1/3*3=1 false (28-digit repeating); &
coercion; month-end clamps (@2012-01-31+1mo→02-29, leap+1yr→Feb28); UCUM week;
time+90min→T12:00; ms-precision adds; quantity composition (303'cm', 36'cm2',
4.0'cm'); div/mod-by-zero, empty, mixed-type, multi-item row-resilient;
birthDate-1yr anchor.

Evidence: .temp/qa/speccomp2/fp18_skeptic_probe1.py
