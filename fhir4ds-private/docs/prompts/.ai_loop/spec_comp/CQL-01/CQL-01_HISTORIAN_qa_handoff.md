# QA Handoff — CQL-01 HISTORIAN

## Verdict: CLEAN — 15/15 fresh cases, 0 flags (normative walk)

Integer add returns Integer; Integer+1 overflow -> NULL (spec null-on-overflow,
observed identical both engines); Decimal max-precision 20+8-digit literal exact;
Long max/min; implies/xor; string concat/empty; implicit Decimal promotion; Integer
/ -> Decimal(38,8) with scale-8 rendering (2.5); Truncate(-1.5) = -1; unary minus
on String -> BinderException BOTH; Boolean*2 -> TranslationError BOTH.

Evidence: .temp/qa/speccomp2/cql01_historian_probe1.py
