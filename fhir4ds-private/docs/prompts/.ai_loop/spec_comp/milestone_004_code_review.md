# Milestone-4 Code Review — chunks FP-16..FP-20 (2026-10-02)

## Scope audit (evidence re-verification)
- FP-16 (§6.4 union/in/contains): passed 0/0/0 — ~74 fresh cases; adjudication = CQL-style
  non-empty list literals are NOT FHIRPath grammar (| builds collections).
- FP-17 (§6.5 boolean): passed 0/0/0 — 129 fresh cases; absorbing-cell doctrine
  ({} and false → false, {} or true → true) fixture-pinned :1140/:1147.
- FP-18 (§6.6/§6.7 arithmetic): passed 0/0/0 w/ FINDING FP-18-F01 (Boolean×Quantity
  fallback-accepts / native-rejects; isolation matrix m3077; native is §6.6-aligned side;
  fix direction: Boolean guard in fallback quantity-multiply arm, engine/invocations/math.py).
- FP-19 (§7/§8 aggregate+lexical): passed 0/0/0 — 75 fresh cases; canonical
  aggregate-init = $total.empty() spelling; div truncates Decimal (fixture testDiv4);
  -3.abs() precedence (testPrecedence1).
- FP-20 (§9-§12 env/reflection/type-safety/grammar): passed 0/0/0 — ~68 fresh cases;
  is_valid(runtime-type-error)=True doctrine re-verified.

## Standing suites re-verified FRESH in this worktree
- environment/type parity + boolean logic + aggregate/lexical + arithmetic:
  307 passed (132s).

## Open findings ledger (all findings-only, human triage, no patches per dispatch rule 4)
1. FP-10-F01 (LOW): matches() 's'-flag — native lenient no-op vs fallback strict reject
   (spec §5.6.9 defines only m/i). Fix = native flag-validation + parity pin.
2. FP-14-F01 (LOW): temporal FIELD vs non-date-shaped-string ordering — native
   lexicographic vs fallback strict-§6.2-empty. Fix = native type-check before coercion.
3. FP-18-F01 (LOW): Boolean×Quantity multiply — fallback coerces via quantity arm,
   native rejects. Fix = Boolean guard in fallback engine/invocations/math.py
   quantity-multiply (Python-only, safe) + parity pin.

## Verdict: MILESTONE PASS (20/58 chunks; 0 bugs; 3 open LOW findings; doctrine hygiene only)
