# QA Handoff — FP-11 HISTORIAN (§5.7 Math)

## Verdict: CLEAN — zero defects (31 fresh cases; 3 MISS all probe-expectation errors)

Normative rows: abs/floor/ceiling directional negatives; exp/ln/log transcendental
BOUNDS checks (transcendental results are floating-point: log(1000,10) → 2.9999999999999996
BOTH engines byte-identical — exact =3 expectations are probe errors); round half-away
table (0.5→1, -0.5→-1, 2.5→3, 1.005@2→1.01); round(3.14, {}) → [] (empty-arg
propagation §4.4.1); truncate Integer typing (1.truncate() is Integer → true,
.type().name → 'Integer' per fixtures testTruncate1); quantity forms keep units
(ceiling/floor/round/truncate); multi-item/empty propagation.

MISS adjudications: log(1000,10)=3 expectation wrong (transcendental); round
empty-precision-arg → [] not default-0; truncate type expectations inverted.

Evidence: .temp/qa/speccomp2/fp11_historian_probe1.py
