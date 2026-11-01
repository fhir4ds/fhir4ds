# QA Handoff — FP-20 SKEPTIC

## Scope
FHIRPath N1 §9 Environment Variables, §10 Types and Reflection, §11 Type Safety, and §12 Formal Specifications. SKEPTIC pass challenged environment variable scoping, undefined variables, `%context`/`%resource`/`%rootResource`, `defineVariable()` leakage/redefinition, `type()` reflection, `ofType`/`is`/`as` consistency, malformed type specifiers, and grammar rejection.

## Fresh Probe
Created `.temp/qa/fp20_skeptic_probe.py` and compared native C++ DuckDB registration with a forced Python fallback registration. The probe covered public result UDFs plus `fhirpath_is_valid()`.

## Finding
- `QA-001` MEDIUM SPEC_VIOLATION: native C++ accepted argument-bearing `type()` calls such as `type(false)` and `1.type(false)` and returned TypeInfo, while the fallback rejected them. FHIRPath N1 §10.2 defines `type()` as the reflection function without parameters, and the local fallback invocation registry enforces arity `{0: []}`. Public native result UDFs should return empty/NULL and `fhirpath_is_valid()` should return false for malformed calls.


- `QA-002` MEDIUM SPEC_VIOLATION: native C++ accepted malformed `defineVariable()` calls, including missing name, non-String name, empty name expression, and too many arguments. The forced Python fallback registry correctly requires `defineVariable(name : String [, value : expression])`. The public native wrappers should return empty/NULL and `fhirpath_is_valid()` should return false for those malformed calls.

## Notes
The broader TypeInfo object currently exposes the public `name` and `namespace` fields used by official R4 conformance and existing parity tests. Full STU metamodel expansion (`baseType`, `element`, collection/tuple variants) remains architecture-sensitive and was not mixed into this surgical arity finding.
