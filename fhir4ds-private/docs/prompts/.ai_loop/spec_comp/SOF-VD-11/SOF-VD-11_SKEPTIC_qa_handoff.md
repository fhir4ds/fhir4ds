# QA Handoff — SOF-VD-11 SKEPTIC (end-to-end execution)

## Verdict: CLEAN — 7/7 fresh dual-path cases (flagged=0 after 1 want fix)

Verified: simple Patient view (3 rows incl. None gender); Observation view
(status + valueQuantity.value string render); address unrolling via forEach
(p1 Springfield+Shelbyville); filtered Observation (where status='final');
cross-resource shared-table filtering (resourceType isolation); typed column
coercion (date->VARCHAR, boolean->BOOLEAN DuckDB types); array collection
column (name.given -> [John,Kim]/[Kim]/[] per patient).

Adjudication: x2 valueQuantity.value renders STRINGS for untyped columns
('120'/'80') — parity holds; want corrected.

Official spec_tests parity (144 tests inside the 465-test compliance file):
FRESH RERUN 465 passed in 7.08s (.temp/qa/speccomp2/sofvd11_official.log).

Evidence: .temp/qa/speccomp2/sofvd11_skeptic_probe1.py
