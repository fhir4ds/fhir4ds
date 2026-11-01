# QA Handoff - CQL-02 EXPLORER

## Scope

Personality: EXPLORER

Chunk: CQL-02, clinical types. I tested pathological combinations after the
SKEPTIC and HISTORIAN passes: clinical `is`/`as` chains, ValueSet
`codesystems` overrides through Vocabulary assertions, Code/Concept aliases
through `as Any`, malformed `ToConcept` inputs, and static Concept equivalence
against inline Concept instances.

Spec basis used:
- CQL 1.5.3 Appendix B: `CodeSystem` and `ValueSet` are structured
  `Vocabulary` subtypes; `Vocabulary` is their abstract base type.
- CQL 1.5.3 clinical values: `Concept` is a list of semantically equivalent
  `Code` values; Concept equivalence is satisfied by shared Code identity.

## Findings

1. `QA-001` HIGH: `ValueSet as Vocabulary` and `CodeSystem as Vocabulary`
   lost concrete subtype identity for downstream `is ValueSet`,
   `as ValueSet`, `is CodeSystem`, and `as CodeSystem`.

2. `QA-002` HIGH: static `Concept { codes: { ... } }` equivalence did not
   extract the nested Code list and returned false for Concepts sharing the
   same system+code.

3. `QA-003` MEDIUM: static clinical aliases through `as Any` translated
   downstream `as Code` / `as Concept` assertions as standalone
   patient-correlated CTE lookups, which fail for direct `translate_cql()`
   expression execution.

## Reproducer

The fresh probe lives at `.temp/qa/cql02_explorer_probe.py`. It compares
native-loaded DuckDB registration against forced Python fallback registration.

Initial failing examples included:
- `define VSAsVocab: VS as Vocabulary`
- `define VSAsVocabIsVS: VSAsVocab is ValueSet`
- `define ConceptIntersectEq: CA ~ Concept { codes: { Code { code: 'b', system: 'http://example.org/cs' } } }`
- `define ConceptAsAnyAsConcept: ConceptAsAny as Concept`

The engineer fixed all three issues in this iteration.
