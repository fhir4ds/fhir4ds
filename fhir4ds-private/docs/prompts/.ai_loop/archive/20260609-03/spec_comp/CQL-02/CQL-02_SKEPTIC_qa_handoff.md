# QA Handoff: CQL-02 SKEPTIC

Scope: CQL clinical types: Code, Concept, ValueSet, CodeSystem, and Vocabulary. I used fresh probes rather than archived CQL-02 outputs and checked translated CQL plus public DuckDB helper behavior across forced Python fallback and native-loaded C++ registration.

Findings:
- `QA-001` HIGH: Declared clinical parameter types were not feeding static clinical type resolution. `parameter P ValueSet default VS; P is Vocabulary` and `P as Vocabulary` fell through to FHIR `resourceType` probing of structured CQL ValueSet JSON and returned SQL NULL instead of true/value.
- `QA-002` HIGH: `ToConcept({ Code ... })` translated to `ToConcept(VARCHAR[])`, but neither backend exposed a list-compatible `ToConcept` surface, causing a binder error.
- `QA-003` HIGH: `ToConcept(Code)` omitted `Concept.display`, accepted malformed non-Code JSON, and null clinical membership in ValueSet/CodeSystem returned NULL or invalid generic SQL instead of false.

Spec basis: CQL 1.5.3 Appendix B defines `ValueSet` and `CodeSystem` under `Vocabulary`, `Code`/`Concept` as distinct clinical values, `ToConcept(Code|List<Code>)`, and terminology membership over a null code argument as false.
