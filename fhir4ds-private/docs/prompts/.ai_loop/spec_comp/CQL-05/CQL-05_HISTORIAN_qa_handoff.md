# QA Handoff — CQL-05 HISTORIAN

## Verdict: CLEAN — 15/15 fresh cases, 0 flags (normative walk)

Coalesce first-non-null semantics (null→'fallback', 'first' wins, variadic);
is-null family over absent fields; ConvertsTo* boolean surface; ToString
primitives; convert...to forms; is-type checks incl. Any root.

Evidence: .temp/qa/speccomp2/cql05_historian_probe1.py
