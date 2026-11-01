# QA Handoff — CQL-02 EXPLORER (Code/CodeSystem/Concept/ValueSet/Vocabulary)

## Verdict: CLEAN — 26/26 fresh fuzz cases, 0 parity diffs (seed 20261002)

Code concat, ToConcept chains, Concept ~ nested/disjoint, codes-of-codes literals,
membership triples, cross-membership, as-chains, Vocabulary-cast-is, VS id length,
display access, concept display null, empty Concept, union-distinct codes, code
equality, concept equivalence order-insensitive, versioned-vs-plain id + 6 seeded
random chains. 4 ERR rows adjudicated PROBE ARTIFACTS: iif() is not CQL grammar
(CQL uses if..then..else); one where-over-codes row hit a probe-pattern internal
error BEFORE evaluation (identical pre-eval on both — not an engine diff); two
random chains generated invalid expressions.

Evidence: .temp/qa/speccomp2/cql02_explorer_probe1.py
