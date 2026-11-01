# QA Handoff — FP-16 HISTORIAN (§6.4)

## Verdict: CLEAN — 19/19 fresh normative cases, 0 flags

Spec-verbatim testUnion group (:1090-1093); union commutative dedup + int-decimal
collapse; in/contains member + non-member + converse identity; §6.4.2/§6.4.3 empty
propagation corner pairs (left-empty propagates / right-empty in→false; right-empty
contains propagates / left-empty→false); singleton scalar operands; equality-backed
membership (1 in 1.0-union true; quantity cross-unit; temporal).

Evidence: .temp/qa/speccomp2/fp16_historian_probe1.py
