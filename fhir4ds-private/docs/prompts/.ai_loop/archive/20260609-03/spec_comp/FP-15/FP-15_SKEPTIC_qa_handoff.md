# QA Handoff - FP-15 SKEPTIC

Chunk: FP-15 FHIRPath Section 6.3 Types.
Personality: SKEPTIC.
Spec source: HL7 FHIRPath Normative Release v2.0.0, sections 3.2, 4.1, 6.3.1-6.3.4, and 10.2.1.

Source-first hypotheses:
- `System.Any` is validated as a type but not wired into native or fallback type hierarchy matching.
- Primitive choice values such as `Observation.valueInteger` may be treated differently by exact `as()` when the type specifier is the capitalized choice suffix form.
- Unknown type specifiers could be hidden by empty inputs or wrapper shortcuts.
- Function syntax `is(type)` / `as(type)` may diverge from infix syntax.
- FHIR primitive `as()` could accidentally use subtype semantics even though existing R4 behavior treats primitive casts as exact.

Fresh probe:
- Created `.temp/qa/fp15_skeptic_probe.py`.
- Ran native C++ DuckDB registration and forced Python fallback registration in separate connections.
- Covered primitive literals, resource and complex values, Quantity/Date types, choice values, unknown types, wrong arity, empty propagation, multi-item row resilience, and function/infix forms.

Findings:
- `QA-001` MEDIUM: `System.Any` is treated as valid but never matches. Both native and fallback returned false/empty for `1 is System.Any`, `1.as(System.Any).exists()`, `Patient is System.Any`, and analogous primitive/complex cases.
- `QA-002` MEDIUM: forced Python fallback loses choice primitive `as(Integer)` semantics when chained. Native returned true for `value.as(Integer).exists()` on `Observation.valueInteger`; fallback returned false.

Notes:
- Probe expectations for data-dependent `arr is Integer` validity were corrected mentally: public `fhirpath_is_valid()` can remain true for data-dependent singleton errors while result UDFs return NULL.
- `value as Quantity` was also a probe expectation issue when checked through `fhirpath_bool`; empty assertion result materializes as NULL, not boolean false.
