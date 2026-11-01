# CQL-05 EXPLORER QA Handoff

## Scope

Chunk CQL-05: structural type operators `As<T>`, `Children`, `Convert to<T>`, `Descendants`, and `Is<T>`.

This EXPLORER pass independently probed the current code state left by SKEPTIC and HISTORIAN. It did not use archived prior output as evidence. It compared native-loaded DuckDB registration with a forced Python fallback registration.

## Findings

1. `Children()`/`Descendants()` list results did not support `is/as List<Any>` and typed list assertions for structural traversal output.
2. Primitive identity for temporal and Long children needed preservation through structural traversal, not plain `VARCHAR[]` coercion.
3. Structural traversal of Code and Concept children needed runtime `is/as` shape checks without accepting mismatched primitive children.
4. `convert List<Code> to Concept` and `convert Concept to List<Code>` lowered but had no registered DuckDB UDF implementations.
5. The test helper named "python only" was actually loading the native FHIRPath extension, so forced fallback parity was not being tested.
6. Forced Python FHIRPath fallback diverged from native choice-field `is/as` and exposed a direct CodeableConcept equivalence gap for `O.value as Concept ~ Code`.

## Verification

- Focused structural parity pytest: `8 passed`.
- Related FHIRPath/CQL parity pytest: `71 passed`.
- DQM targeted subset: `12/12 perfect`, 716 patients.
- Broad CQL pytest: `4915 passed, 5 skipped`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.
- Full `fhir4ds/` pytest: `7148 passed, 5 skipped`.
- `git diff --check`: clean.
