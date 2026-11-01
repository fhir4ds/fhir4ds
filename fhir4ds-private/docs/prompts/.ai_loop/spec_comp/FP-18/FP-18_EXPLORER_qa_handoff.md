# QA Handoff — FP-18 EXPLORER (§6.6/§6.7 Arithmetic)

## Verdict: 1 finding (FP-18-F01 LOW, findings-only) — 31/32 clean, 1 parity diff

### FP-18-F01: Boolean × Quantity accepted by FALLBACK, rejected by NATIVE
`true * 5 'mg'` → native [] (row-resilient error) vs fallback ["5 'mg'"].
Isolation matrix: `true * 5`, `true + 1`, `false * 5` → [] BOTH engines; ONLY the
Boolean×Quantity corner diverges. The fallback core's quantity-multiply arm
coerces Boolean→1 (the FP-18 HISTORIAN 2026-06-30 bool-coercion fix patched the
SCALAR +,-,*,/,div,mod paths but missed the Quantity-operand multiply arm).
Per §6.6 Boolean is not a defined arithmetic operand → NATIVE is the
spec-aligned side. Unpinned by any fixture. Fix direction (human triage):
Boolean guard in the fallback quantity-multiply arm (engine/invocations/math.py)
+ a parity pin. NOT patched per findings-only discipline.

Everything else clean: 8-term chains, paren towers, & towers, int32-min-1, big
products, 28-digit adds, tiny division decimals, date+date/time+days/qty+bare
rejections, concat edges, scalar rejections, temporal compositions, iif
containment, where-over-arith, 8 seeded randoms (seed 20261002).

Evidence: .temp/qa/speccomp2/fp18_explorer_probe1.py
