# QA Handoff - FP-15 HISTORIAN

## Scope

Fresh HISTORIAN pass over FHIRPath Normative Release §6.3 Types:
- `is type specifier`
- `is(type)`
- `as type specifier`
- `as(type)`

Official spec consulted: FHIRPath Normative Release §6.3.1-§6.3.4 and §10.1. The key rule is that type specifier arguments are optionally qualified identifiers that must resolve to a model type; unresolved type identifiers are errors. Public DuckDB UDFs are expected to convert those row-level errors to empty/NULL, while `fhirpath_is_valid` should return false.

## Probes

- Built a fresh `.temp/qa/fp15_historian_fresh/` probe matrix covering operator and function forms, System literals, FHIR JSON primitives, resource/complex supertypes, FHIR choice types, empty input, multi-item singleton errors, unknown types, missing type arguments, and qualified model names.
- Explicitly tested native C++ DuckDB extension registration and forced Python fallback registration.
- Compared `fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, and `fhirpath_is_valid` surfaces.

## Finding

QA-001: `FHIR.Boolean`, `FHIR.Integer`, and related FHIR-qualified System primitive aliases were treated as valid type specifiers. This violates §6.3/§10.1 model-qualified type resolution: FHIR model primitive names are lowercase (`FHIR.boolean`, `FHIR.integer`), while System primitive names are capitalized (`System.Boolean`, `System.Integer`). Public UDFs should return empty/NULL and `fhirpath_is_valid=false` for these unresolved FHIR-qualified aliases.

Severity: HIGH  
Category: SPEC_VIOLATION  
Status at QA handoff: OPEN

Important control: official R4 conformance expects `Patient.is(System.Patient).not()` to return true. `System.Patient` must remain a resolvable non-match, not an invalid expression.
