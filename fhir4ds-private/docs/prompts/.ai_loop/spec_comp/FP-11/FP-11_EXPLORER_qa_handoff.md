# QA Handoff — FP-11 EXPLORER (§5.7 Math)

## Verdict: CLEAN — 39/39 fresh fuzz cases, 0 parity diffs

Extreme magnitudes (int32 max/min abs, 28-digit decimals, 10^20/10^-5/2^1024 powers,
exp(100), ln(1e-7), sqrt(1e14)/sqrt(1e-8), round@28/negative-precision); error domains
(ln 0, sqrt neg, log neg base, 0^-1) row-resilient symmetric; chains (abs→sqrt,
ceiling→floor, truncate→abs, round→power, exp→ln roundtrip, sqrt→power bounds,
iif error containment both directions); typed edges (string/bool/date/multi-item/empty
→ empty both); quantity compositions (qty power/ln); 8 seeded randoms (seed 20261002).

Evidence: .temp/qa/speccomp2/fp11_explorer_probe1.py
