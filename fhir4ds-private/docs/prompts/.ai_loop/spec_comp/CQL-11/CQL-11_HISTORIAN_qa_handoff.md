# QA Handoff — CQL-11 HISTORIAN

## Verdict: CLEAN — normative-walk rows parity-OK

Round negative-tie away-from-zero (-0.5->-1); Truncate->Integer toward zero;
Precision scale-after-scale-8-rounding (1.587 -> 3); Max/Min Quantity
element-in-own-unit; successor/predecessor lexical precision preservation;
Modulo dividend-sign; Power exact Integer; unary-minus negation.

Evidence: SKEPTIC battery + /tmp/opencode/cql11_adj.py (all rows native==fallback)
