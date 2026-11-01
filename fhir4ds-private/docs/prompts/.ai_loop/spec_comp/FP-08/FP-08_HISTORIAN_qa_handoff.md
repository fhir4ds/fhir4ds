# QA Handoff — FP-08 HISTORIAN (§5.5.7-§5.5.9)

## Verdict: CLEAN — zero defects (17 fresh cases; 1 MISS adjudicated probe-expectation)

Spec-verbatim rows: conversion factors (1 year=12 month, 1 minute=60 seconds,
1 'min'=60 's', toQuantity unit forms); quantity string form '4 days'.toQuantity()
→ ['4 days'] — the CALENDAR KEYWORD IS PRESERVED PLURAL in output (fixtures
tests-fhir-r4.xml:409-412 pin '1 day'.toQuantity() = 1 day; my singular
expectation was wrong — both engines identical); toString table rows; toTime
string forms incl. bare '14'/'14:34' (fixtures :351-352); resource round-trips.

Evidence: .temp/qa/speccomp2/fp08_historian_probe1.py
