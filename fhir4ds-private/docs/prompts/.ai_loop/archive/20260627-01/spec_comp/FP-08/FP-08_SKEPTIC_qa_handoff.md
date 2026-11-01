# QA Handoff - FP-08 SKEPTIC

Spec chunk: FHIRPath §5.5.7 Quantity Conversion, §5.5.8 String Conversion, §5.5.9 Time Conversion.

Personality: SKEPTIC.

Spec source consulted: official HL7 FHIRPath continuous-build source, `input/pages/index.md`, especially the function argument rules and §5.5.7-§5.5.9 conversion definitions.

Hypotheses probed:
- Native and fallback may disagree on sourced `toQuantity([unit])` and `convertsToQuantity([unit])` calls when `unit` is a dynamic sibling path rather than a literal.
- Resource-backed FHIR Quantity values may serialize or convert differently between native and fallback.
- Time conversion may accidentally promote partial precision or accept malformed values.
- FP-08 exact arity/singleton guards may regress through public wrapper UDFs.

Fresh probe:
- `.temp/qa/fp08_skeptic_fresh_probe.py`

Finding:
- `QA-001` MEDIUM OPEN: native DuckDB/C++ evaluates dynamic Quantity conversion `unit` arguments against the source value instead of the outer invocation context. Forced Python fallback correctly resolves sibling unit paths such as `targetUnit`.

Evidence:
- Native returns empty/NULL for `value.toQuantity(targetUnit)`, `value.convertsToQuantity(targetUnit)`, `quantityText.toQuantity(targetUnit)`, and `items.select(quantityText.toQuantity(targetUnit))`.
- Forced Python fallback returns converted results such as `0.005 'g'`, `true`, `1000 'g'`, and `[1000 'g', 1 'g']`.

Adjacent checks that passed in the same probe:
- Literal-unit Quantity conversion.
- Resource-backed Quantity conversion and stringification.
- Invalid Quantity shape rejection.
- Partial Time precision preservation.
- Malformed Time conversion false/empty behavior.
- Existing singleton/arity guards for `(1|2).toString()` and empty optional unit arguments.
