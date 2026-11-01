# QA Handoff: CQL-02 HISTORIAN

Scope: CQL clinical terminology types: `Code`, `CodeSystem`, `Concept`,
`ValueSet`, and `Vocabulary`, including native-loaded versus forced Python
fallback DuckDB execution.

Spec basis checked:
- CQL 1.5.3 Appendix A `valuesetDefinition` permits optional
  `codesystems { codesystemIdentifier, ... }`.
- CQL 1.5.3 Appendix B defines `ValueSet : Vocabulary` with
  `codesystems List<CodeSystem>`, and defines `Vocabulary` as the common
  reference type for `ValueSet` and `CodeSystem`.

Fresh probe:
- `.temp/qa/cql02_historian_probe.py`

Finding:
- `QA-001` HIGH: `valueset ... codesystems { ... }` failed to parse with
  `ParseError: Unexpected token IDENTIFIER 'codesystems'`. The parser stopped
  after ValueSet id/version, and structured `System.ValueSet` output could not
  preserve CodeSystem override metadata.

Other clinical-type checks in the probe exercised:
- `ValueSet`/`CodeSystem` as `Vocabulary`, with `Code`/`Concept` excluded.
- `ToConcept(Code)` and `ToConcept(List<Code>)` shape and display/version
  preservation.
- `Concept ~ Code` equivalence across multiple codes.
- Forced Python fallback and native-loaded DuckDB parity for translated SQL.
