# QA Handoff — CQL-02 SKEPTIC (Code/CodeSystem/Concept/ValueSet/Vocabulary)

## Verdict: CLEAN — 23+ fresh dual-path cases, 0 defects

probe1b: code basics (code/system/display), C1 is Code, Concept codes List<Code>
+ Count=2, ToConcept(C1) Count=1, vocabulary-splits matrix (VS is ValueSet true /
CS is CodeSystem true / VS is CodeSystem false / CS is ValueSet false — CQL-21
doctrine), C1 is Vocabulary false. 2 EXC rows ADJUDICATED MY spelling: bare V1
identifier parses as path -> BinderException identical both engines; the QUOTED
decl-name form works on both (probe1c 5/5: "V1".id, "V1" is ValueSet, "LOINC".id,
retrieve-with-valueset-name, string-URL). probe2 (10/10): static membership
(own-CS true / other-CS false / empty-VS false), Concept ~ codes-intersection
semantics (same true / single true / disjoint false), ToConcept(List<Code>)=2,
versioned-CS decl + code reference works.

Evidence: .temp/qa/speccomp2/cql02_skeptic_probe1b.py + probe1c + probe2
