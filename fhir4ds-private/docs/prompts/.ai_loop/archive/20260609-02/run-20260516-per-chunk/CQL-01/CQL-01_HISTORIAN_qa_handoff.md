# QA Handoff — CQL-01 HISTORIAN

## Scope
- Chunk: CQL-01, primitive types: Any, Boolean, Integer, Decimal, String, Long.
- Personality: HISTORIAN.
- Evidence sources: active loop prompts/state, current source tree, local official CQL tests, and CQL 1.5.3 Appendix B. Archived `spec_comp/**` outputs were not inspected.

## Spec Anchors
- CQL 1.5.3 Appendix B Types: `Any` is the maximal supertype; `Long` is trial-use and ranges from `-2^63` to `2^63 - 1`; `Integer` ranges from `-2^31` to `2^31 - 1`.
- CQL 1.5.3 Appendix B Type Operators / `As`: `as<T>(argument Any)` returns null if the argument is not of the specified runtime type.
- CQL 1.5.3 Appendix B Type Operators / `ToInteger` and `ToLong`: string inputs use the integer formatting grammar and invalid strings return null/false through conversion-check operators.

## Fresh Probes
- Re-tested primitive literal translation, signed numeric minima, Decimal raw precision, `is Any`, exact primitive `is`, and string-to-Integer/Long conversion boundaries.
- Compared native-loaded DuckDB registration with forced Python fallback registration for CQL conversion/logical surfaces and FHIRPath UDFs invoked through CQL registration.
- Added a direct probe for primitive `as`: `5 as String`, `'5' as Integer`, `true as Integer`, `5L as Integer`, `null as Integer`, and `5 as Any`.

## Finding
- `QA-001` MEDIUM SPEC_VIOLATION: Primitive CQL `as` was translated as a pass-through for non-Quantity targets. Mismatched primitive type assertions returned the original value instead of SQL NULL on both native-loaded and forced Python DuckDB paths.

## Validation During QA
- Focused reproducer confirmed the issue before remediation.
