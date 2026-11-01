# QA Handoff — CQL-19 EXPLORER (list operators Part 2, adversarial)

## Verdict: CLEAN — same battery, adversarial angles (boundary counts,
clamps, dynamic-source singleton, Decimal list Last), 0 parity diffs.

Skip 0 identity / Take 5 over-count clamp / singleton-from-single-element-
dynamic-source / mixed Decimal list Last — all parity-identical with
correct values on both engines.

Evidence: .temp/qa/speccomp2/cql19_historian_explorer_probe1.py
