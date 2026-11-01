# QA Handoff — FP-16 EXPLORER (§6.4)

## Verdict: CLEAN — 28/28 fresh fuzz cases, 0 parity diffs

8-term union chains (first-occurrence dedup verified), heterogeneous unions
(int|string|bool; temporal+string), mixed-collection membership, emoji/unicode dedup,
quantity dimension-mismatch + tolerance membership, deep-object membership
(name.first() in name), in/contains inside where/select, iif containment,
double-union collapse, empty chains, precision-mismatch temporal, tz-equal instant
membership, 8 seeded random left×right compositions (seed 20261002).

Evidence: .temp/qa/speccomp2/fp16_explorer_probe1.py
