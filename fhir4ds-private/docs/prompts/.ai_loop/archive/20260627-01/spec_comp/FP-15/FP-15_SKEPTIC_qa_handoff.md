# QA Handoff - FP-15 SKEPTIC

Chunk: FP-15, FHIRPath §6.3 Types  
Personality: SKEPTIC  
Spec source: HL7 FHIRPath continuous-build source, §6.3 Types.

## Hypotheses Tested

- Native and fallback type-specifier validation may drift from the R4 model hierarchy.
- `is`/`as` function and operator forms may disagree across primitive, resource, and choice values.
- Public DuckDB wrappers may classify runtime singleton errors, empty input, and invalid type specifiers inconsistently.
- Review-10's split native FHIR type-specifier coverage risk may intersect this chunk.

## Fresh Probe

Created `.temp/qa/fp15_skeptic_fresh_probe.py`.

The probe compares native C++ DuckDB registration against forced Python fallback across 27 expressions covering:
- primitive `is`, `is()`, `as`, and `as()` forms;
- empty and multi-item operands;
- invalid type specifiers;
- FHIR resource and supertype checks;
- choice type values after `ofType(Observation)`;
- review-10 resource specifiers: `CodeSystem`, `QuestionnaireResponse`, `Binary`, and `Parameters`.

## Findings

### QA-001 - MEDIUM - SPEC_VIOLATION

Valid R4 resource type specifiers were rejected by public DuckDB FHIRPath surfaces.

Examples before remediation:
- `entry.resource.ofType(CodeSystem).id`
- `entry.resource.ofType(QuestionnaireResponse).id`
- `entry.resource.ofType(Binary).id`
- `entry.resource.ofType(Parameters).id`

Actual: empty/NULL results with `fhirpath_is_valid=false`.  
Expected: the matching resource IDs with `fhirpath_is_valid=true`.

Spec basis: §6.3 type specifiers must resolve against the model type system; these are valid R4 resource types and appear in the local R4 hierarchy metadata.

### QA-002 - MEDIUM - SPEC_VIOLATION

Forced Python fallback lost choice type metadata after a source expression.

Examples before remediation:
- `entry.resource.ofType(Observation).value.is(Integer)`
- `entry.resource.ofType(Observation).value.as(Integer)`

Actual fallback: `false` / empty.  
Expected: `true` / `5`, matching native and the `valueInteger` choice type.

Spec basis: §6.3 `is` returns true when the singleton input is of the specified type, and `as` returns the input item when it is of that type.

## Status

Issues logged in `evolution.json` and handed off for remediation.
