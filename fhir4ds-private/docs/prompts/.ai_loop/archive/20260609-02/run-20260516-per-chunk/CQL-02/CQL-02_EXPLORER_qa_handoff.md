# QA Handoff - CQL-02 EXPLORER

Personality: EXPLORER
Iteration: 1
Scope: CQL clinical types Code, CodeSystem, Concept, ValueSet, Vocabulary.

## Spec Anchors

- CQL 1.5.3 Appendix B defines Code as a structured clinical code value.
- Concept is a structured value with `codes List<Code>` and optional display.
- ValueSet and CodeSystem are Vocabulary subtypes.
- Clinical `~` supports Code/Code, Concept/Concept, Code/Concept, and Concept/Code. Code equivalence compares code+system and ignores version/display; Concept equivalence is non-empty intersection by Code equivalence.
- `in ValueSet` and `in CodeSystem` are terminology membership boundaries.

## Exploration

- Probed compile-time Code/Concept equivalence with containing and disjoint concepts.
- Probed dynamic FHIR CodeableConcept comparison against a named Concept.
- Probed clinical type aliases through definitions and query `let`/`return`/`singleton from`.
- Compared DuckDB-backed execution through native-loaded registration and forced Python fallback registration for regression cases.

## Findings

1. `CQL02-EXPLORER-001` HIGH: Concept equivalence flattened concepts as single code dictionaries. This made Code ~ containing Concept false, Concept ~ containing Code false, disjoint concepts true, and dynamic FHIR CodeableConcept ~ Concept compile to `code.coding.exists()` without target code predicates.

2. `CQL02-EXPLORER-002` MEDIUM: Clinical type metadata was not inferred through `singleton from` query returns and query `let` aliases. Static clinical values returned by queries fell through to FHIR `resourceType` probing.

## Reproducer

Probe script: `.temp/qa/cql02_explorer_probe.py`

Initial actuals included:

- `"Systolic" ~ "Blood Pressure"` -> `FALSE`
- `"Blood Pressure" ~ "Systolic"` -> `FALSE`
- `"Blood Pressure" ~ "Diastolic Pressure"` -> `TRUE`
- `O.code ~ "Blood Pressure"` -> `code.coding.exists()`
- `singleton from ([Observation] O return "Blood Pressure") is Concept` -> JSON `resourceType` check

Regression coverage should live in `fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`.
