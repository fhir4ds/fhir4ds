# FP-04 SKEPTIC Engineer Handoff (iteration 1, 2026-08-17)

## Triage
- QA-001 MEDIUM SPEC_VIOLATION (parity, §5.2.4/§6.3.1/§6.3.3) — CONFIRMED,
  fixed, RESOLVED.
- QA-002 LOW — INTENDED (no change; spec-correct non-match of
  System.String on FHIR strings, both engines agree).

## QA-001 fix
Root cause: native `fn_isType` FHIR branch (and the `type()` reflection
site) had no structural complex-type inference and blanket-inferred
`BackboneElement` for ANY JSON object under a known field name; the
Python fallback structurally detects complex types
(nodes.py `TypeInfo.create_by_value_in_namespace`) and reports
`FHIR.object` for unknown objects.

Change (extensions/fhirpath/src/fhirpath/evaluator.cpp): new
`structuralFHIRComplexType(yyjson_val*, const std::string&)` helper
mirroring the Python inference order (coding→CodeableConcept;
system&code&!value→Coding; value&(unit|code)→Quantity; reference→
Reference; contentType→Attachment; low|high→Range; start|end→Period;
known backbone fields {communication, component, compose, contact,
expansion, item, link}→BackboneElement, sourced from
models/r4/fhir_path_to_type.json full-path entries). Wired into:
1. `fn_isType` FHIR branch (covers `is`, `as`, `ofType`),
2. `type()` reflection default branch (unknown objects now `FHIR.object`,
   matching the fallback).
Extension rebuilt (`make fhirpath_loadable_extension`) and deployed to
`fhir4ds/fhirpath/duckdb/extensions/` and site-packages.

Regression test:
`test_structural_complex_type_tests_match_cpp_fp04_skeptic` in
fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py
(17 dual-path expressions incl. backbone preservation + count pins).

## Validation
- probe.py 61/61 parity, probe2.py 23/23 parity, 27-case blast-radius
  battery 0 parity fails (incl. `contact.is(BackboneElement)` still
  true in both engines).
- fhirpath pytest: 1723 passed.
- FULL conformance: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held.

No new issues discovered. No workarounds; fix mirrors the fallback's
existing inference at its root.
