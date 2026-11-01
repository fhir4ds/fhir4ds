# Architect Handoff: CQL-02 SKEPTIC

Structural health: clean after remediation. The fixes preserve the CQL translator's AST/metadata pipeline: clinical parameter typing now flows through `context.lookup_symbol`, `ToConcept(List<Code>)` is routed by SQL AST shape, and null terminology membership is folded before ValueSet/CodeSystem dispatch. The DuckDB fallback macro for `ToConcept(arg)` is confined to the registration boundary to compensate for Python UDF overload limits; native C++ exposes real scalar and list overloads.

Issue summary: 3 HIGH `SPEC_VIOLATION` findings from QA, all resolved and validated. No architect-phase findings were added, and no `RETRY_QA` is warranted because QA covered the requested SKEPTIC clinical boundaries: Code vs Concept, Vocabulary hierarchy, structured clinical JSON, static parameters, null membership, translated CQL execution, direct helper/UDF surfaces, and native-loaded versus forced Python fallback parity.

Validation accepted: `.temp/qa/cql02_skeptic_probe.py` passed; focused clinical/conversion pytest reported 23 passed; native CQL sqllogictest reported 776 assertions passed; full conformance passed 2822/2822 with ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, and DQM 47/47.

Recommended fix order: none. The loop is eligible for a clean exit and return to the outer spec compliance orchestrator.
