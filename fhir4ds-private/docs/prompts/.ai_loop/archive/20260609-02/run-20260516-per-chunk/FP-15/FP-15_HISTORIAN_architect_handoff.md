# Architect Handoff - FP-15 HISTORIAN

## Structural Assessment

The FP-15 type-operator path is structurally sound after remediation. The final design keeps type-specifier validation at the semantic boundary, before public DuckDB wrapper resilience converts evaluator errors to empty/NULL. Native C++ and Python fallback now agree for invalid FHIR-qualified System primitive aliases, official R4 `System.Patient` behavior, and choice-type suffix matching.

## Issue Status

| Severity | Count | Status |
|---|---:|---|
| HIGH | 1 | VERIFIED |
| MEDIUM | 0 | None |
| LOW | 0 | None |

QA quality was sufficient for a HISTORIAN pass: it covered all four §6.3 forms, native and forced Python fallback backends, public scalar/json/bool/validity surfaces, invalid type specifiers, wrong arity, singleton errors, resource/complex supertypes, primitive exactness, and choice-type controls. `RETRY_QA` is not required.

## Architecture Notes

- Golden invariant: qualified type specifiers must resolve in the declared model namespace, but official R4 compatibility requires `System.Patient` to remain a resolvable non-match.
- Golden invariant: `fhirpath_is_valid()` is semantic validation, not parser-only validation; it must evaluate against a sample resource and reject unresolved type specifiers.
- Golden invariant: unqualified choice-type suffixes such as `Integer` in `value.ofType(Integer)` are model metadata, not System primitive matching.

## Recommended Fix Order

No open issues remain. Future type-system work should prioritize replacing hand-maintained native C++ type tables with generated FHIR model metadata before extending type coverage.
