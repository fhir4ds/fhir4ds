# QA Handoff - FP-04 EXPLORER

## Scope

- Workflow: `evolution`
- Phase completed: `QA`
- Iteration: 1
- Personality: `EXPLORER`
- Chunk: SPEC FP-04, FHIRPath §5.2 Filtering and Projection

## Spec Anchor

Official HL7 FHIRPath source §5.2 says:

- `where(criteria)` evaluates criteria per item with `$this` and `$index`; only singleton Boolean `true` keeps an item.
- `select(projection)` evaluates projection per item with `$this` and `$index`, flattens per-item collection results, and elides empty results.
- `repeat(projection)` evaluates projection with `$this`, repeats on newly added items, uses equality-based de-duplication, and does not set a repeat-local `$index`.
- `ofType(type)` returns items of the requested model type or subclass, and the argument must resolve as a model type specifier.

Source: https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

## Fresh Probe

Created `.temp/qa/fp04_explorer_fresh_probe.py` with synthetic Patient,
Questionnaire, Observation, Bundle, and numeric resources. The probe compares
native DuckDB/C++ and forced Python fallback outputs for `where`, `select`,
`repeat`, and `ofType`.

## Finding

Opened `QA-001` (`HIGH`, `SPEC_VIOLATION`).

Native DuckDB/C++ drops valid R4 resource subclasses from
`ofType(Resource)` and `ofType(DomainResource)` because its embedded FHIR type
hierarchy is a small subset of the generated R4 model hierarchy. In the fresh
probe, fallback includes `Questionnaire`, `QuestionnaireResponse`, `ValueSet`,
and `CodeSystem` under the appropriate supertype filters; native excludes them.

## Validation Run

- `python3 .temp/qa/fp04_explorer_fresh_probe.py` failed at the native/fallback
  `ofType(Resource)` divergence before remediation.
