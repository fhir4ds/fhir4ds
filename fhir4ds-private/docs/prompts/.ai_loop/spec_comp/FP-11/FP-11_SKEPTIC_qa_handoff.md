# QA Handoff — FP-11 SKEPTIC (§5.7 Math)

## Verdict: CLEAN — zero defects (39 fresh dual-path cases; 3 MISS all probe-expectation errors)

abs (int/decimal/quantity type preservation, negative quantities); ceiling/floor
(directional rounding incl negatives); exp (e bounds 2.718-2.719); ln (ln 1 = 0,
error domains 0/-1 → row-resilient empty both); log (spec rows log(100,10)=2,
log(8,2)=3, error bases 0/1 empty); power (fixture testPower1/2 green, (-1).power(0.5)
empty per fixture testPower3, Integer result typing via = comparisons); round (half-
away-from-zero 1.5→2/-1.5→-2, precision forms, returns Decimal); sqrt (9→3.0,
bounds-checked sqrt(2), error domain -1 empty); truncate (fixture rows 101, 1.00000001,
-1.56 verified; Integer type).

MISS adjudications: (1) 2.power(4)=16 — MY label said "2^4=8" (arithmetic error;
engines correct); (2) power int-result rendering '16' not '8'; (3) 0.power(0) → []
BOTH engines — spec-silent, error-form consistent with fixture testPower3; no fixture
pins 0^0=1.

Evidence: .temp/qa/speccomp2/fp11_skeptic_probe1.py
