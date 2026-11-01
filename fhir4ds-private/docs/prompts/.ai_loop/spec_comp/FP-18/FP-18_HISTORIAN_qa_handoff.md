# QA Handoff — FP-18 HISTORIAN (§6.6/§6.7 Arithmetic)

## Verdict: CLEAN — zero defects (21 fresh cases; 1 MISS adjudicated)

Adjudication: `-3.abs()` → ['-3'] CORRECT — §6.8 unary minus binds LOOSER than
member access (-(3.abs())); fixture testPrecedence1 pins it; (-3).abs() → ['3'].

Verified: fixture-verbatim div/mod rows (testDiv1/3/4/5); 0.1*3=0.3; 2.5*4.0=10.00
scale; dateTime unit allowlist rejections (@2016-02-29+23h, @2016+1'a',
@2016-02+1'mo', @2015-02-04+1 int all []); calendar Jan31→Feb28 clamp; time-minus
wrap T12:00-90min→T10:30; quantity adds/divides; (-0.4).round()=0.0.

Evidence: .temp/qa/speccomp2/fp18_historian_probe1.py
