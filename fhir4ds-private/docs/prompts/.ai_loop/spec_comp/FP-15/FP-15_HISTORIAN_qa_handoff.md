# QA Handoff — FP-15 HISTORIAN (§6.3)

## Verdict: CLEAN — 24 fresh normative cases; 2 MISS adjudicated (fixture :1507-1534)

Full is/as fixture-group ground truth read: is subtype-based (:1508 gender is string
TRUE), as EXACT on declared primitive (:1511 as(string) on gender expected-EMPTY,
:1512 as(code) → male, :1514 version as(string) KEPT, :1513 as(id) empty). Live
verified: id as FHIR.id → ['p1'] kept both engines; birthDate as FHIR.date kept;
birthDate as FHIR.string empty; gender as FHIR.date empty — identical native/fallback.

Evidence: .temp/qa/speccomp2/fp15_historian_probe1.py
