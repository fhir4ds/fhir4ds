# QA Handoff — FP-20 EXPLORER

Personality: EXPLORER. Scope: FHIRPath N1 Sections 9-12 covering environment variables, type reflection, type safety, formal grammar, and URI/media-type metadata.

Fresh exploration created `.temp/qa/fp20_explorer_probe.py` and compared the native C++ DuckDB extension against the forced Python fallback across 81 public-wrapper expression cases plus 16 explicit validity checks. The probe stressed external constants with hidden comments/escaped identifiers, `%context`/`%resource`/`%rootResource` in nested scopes, `defineVariable()` leakage, chained `type()` results, unknown/qualified types, invalid operands, and R4 URI/media/code fields.

Finding: `QA-001` MEDIUM. Native `Questionnaire.subjectType.type().name` returned `string`, while forced Python fallback returned `code`. FHIRPath N1 Section 10.2 requires `type()` to report model type information, and FHIR R4 defines `Questionnaire.subjectType` as type `code`.

Validation after remediation: FP-20 EXPLORER probe reported `cases=81`, `validity_cases=16`, `mismatches=0`.
