# QA Handoff — CQL-04 HISTORIAN

## Verdict: CLEAN — 17/17 value rows OK; function-form rows adjudicated

Null rows verbatim under the null≡False surface collapse; precedence rows
(not binds tighter than and; and tighter than or/xor; implies lowest; left-assoc);
resource-backed mirrors. `And(true,true)` ParseError correct (function-form NOT CQL
grammar); `Not(true)` parses as unary `not (true)` and evaluates False on BOTH
engines — INTENDED per the pinned CQL-04 parser keyword-identifier leniency doctrine
(parity re-verified via .temp/qa/speccomp2/cql04_not_adjudication.py).

Evidence: .temp/qa/speccomp2/cql04_historian_probe1.py
