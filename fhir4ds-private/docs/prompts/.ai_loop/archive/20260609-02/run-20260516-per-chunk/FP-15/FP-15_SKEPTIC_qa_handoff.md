# QA Handoff - FP-15 SKEPTIC

## Scope
- Chunk: FP-15
- Spec: FHIRPath Normative Release N1 §6.3 Types
- Items tested: `is type specifier`, `is(type)`, `as type specifier`, `as(type)`
- Backend coverage: native C++ DuckDB extension, forced Python DuckDB fallback, and Python core strict evaluator.

## Spec Anchor
HL7 FHIRPath N1 §6.3 says:
- `is` returns true for the requested type or a subclass, false for nonmatching singleton input, empty for other non-error cases, and errors for unresolved type identifiers or multi-item input.
- `as` returns the original singleton input when it is the requested type or a subclass; unresolved type identifiers and multi-item input are errors; other cases return empty.
- `is()` and `as()` are backward-compatible function forms whose arguments are type specifiers, not normal identifier expressions.

## Hypotheses Tested
1. Native parser accepts missing type operands after `is`/`as`.
2. Native type functions silently treat unresolved types as false/empty.
3. Python core `is` does not enforce singleton errors.
4. `as` was implemented as exact type matching rather than subtype matching.
5. Native inferred FHIR complex types do not check superclass relationships.

## Findings
- QA-001 HIGH: `as` rejects valid supertypes (`Patient as DomainResource`, `Patient as Resource`, `name.first() as Element`) despite §6.3 allowing subclass matches.
- QA-002 HIGH: native C++ treats malformed/unresolved type specifiers as valid false/empty expressions (`1 is NoSuchType`, `1 is`, `1.is()`).
- QA-003 MEDIUM: strict Python core and native evaluator return empty rather than signaling an error for multi-item `is` input.
- QA-004 MEDIUM: native C++ returns false for `name.first() is Element`, while Python fallback/core return true.

## Reproducer
Used an inline DuckDB/Python parity probe in `.temp/qa/fp15_skeptic` style workspace against a synthetic Patient resource. Native/fallback differences were observed on `fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, and `fhirpath_is_valid`.

## Next Role
Remediation should fix Python core and native C++ source, rebuild/copy the bundled extension if native code changes, then add focused regression tests covering native and forced fallback behavior.
