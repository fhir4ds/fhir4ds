# Architect Handoff — SOF-VD-05 SKEPTIC

Phase: ARCHITECT
Golden standard: `.temp/architect/golden_standard.md`

Structural assessment:
- No production architecture issue remains open.
- QA was not lazy: it attacked the Domain 5 key risk around `forEachOrNull`, nested select focus, row combination, duplicates, and empty combinations. The main finding was a useful false positive that exposed a subtle boundary, and remediation correctly rejected a test-driven widening after official fixtures regressed.
- The current architecture should keep SQL-on-FHIR row-composition layers distinct: `forEachOrNull` preserves rows for its own expression; descendant `select`, child `forEach`, and `unionAll` keep their normal row-set semantics.

Issue summary:
- QA-001: INTENDED. No production fix. Added a boundary integration test plus AGENTS/GLOBAL_KNOWLEDGE notes.
- New architect findings: 0.
- RETRY_QA: false.

Validation:
- Focused boundary test: 1 passed.
- ViewDefinition pytest: 821 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Full package pytest: 7359 passed, 5 skipped, 9 warnings.

Recommended next step:
- Outer orchestrator may archive SOF-VD-05 SKEPTIC and advance to SOF-VD-05 HISTORIAN.
