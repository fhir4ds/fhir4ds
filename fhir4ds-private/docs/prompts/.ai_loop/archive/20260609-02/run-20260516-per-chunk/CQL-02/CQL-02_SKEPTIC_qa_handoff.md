# CQL-02 SKEPTIC QA Handoff

## Scope

- Chunk: CQL-02 clinical types.
- Personality: SKEPTIC.
- Covered types: `Code`, `CodeSystem`, `Concept`, `ValueSet`, `Vocabulary`.
- Fresh evidence only: active workflow files, source, local tests, and official CQL conformance. No archived `spec_comp/**` outputs were used.

## Findings

### QA-CQL02-SKEPTIC-001 - HIGH - RESOLVED

`Code '8480-6' from LOINC is Code` translated through JSON `resourceType` extraction over a legacy `system|code` string and raised malformed JSON. `ToConcept(Code '8480-6' from LOINC)` returned NULL because the public conversion surface expects a JSON-shaped Code value.

### QA-CQL02-SKEPTIC-002 - MEDIUM - RESOLVED

Clinical `is` checks needed static CQL clinical type identity before generic FHIR resource probing. The failure mode affected clinical constructors and library refs for ValueSet, CodeSystem, Code, Concept, and Vocabulary.

### QA-CQL02-SKEPTIC-003 - MEDIUM - RESOLVED

Clinical `as` assertions accepted mismatched clinical values. `ValueSet as CodeSystem`, `Code as Concept`, and selector Code as Concept returned the source instead of NULL.

### QA-CQL02-SKEPTIC-004 - HIGH - RESOLVED

Architect validation caught the first remediation over-applying static clinical `as` rules to dynamic FHIR values. `Observation.value as Concept ~ "Stage"` compiled to static false conditions when the source type was not known at translation time, dropping DQM conformance to 39/47. Clinical `as` now only short-circuits for statically known clinical source types and leaves dynamic FHIR values on the runtime path.

## QA Evidence

- Native and forced Python fallback probes were compared for clinical constructors, named refs, selectors, `is`, `as`, and `ToConcept`.
- Regression coverage is in `fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`.
- Official CQL conformance passed after remediation: 1706/1706.
- Targeted DQM rerun for CMS646, CMS1056, CMS826, and CMS122 passed 4/4 at 100%.
- Broad CQL unit/integration/DuckDB pytest passed 4894 with 5 skips.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
