# QA Handoff — FP-20 EXPLORER (§9-§12)

## Verdict: CLEAN — 27/27 fresh fuzz cases, 0 parity diffs

Env-var compositions (where/select/iif over %context; union with literal);
reflection chains (type().name equality, type-in-where, is-FHIR.HumanName-in-select);
type-safety towers (error | true propagation, iif containment, where type-error row);
grammar fuzz (6-deep parens, no-space operator chains, trailing comment, backtick
navigation, empty-union identity); pathological deep-missing paths; unicode operands;
8 seeded random atom×fn/op compositions (seed 20261002).

Evidence: .temp/qa/speccomp2/fp20_explorer_probe1.py