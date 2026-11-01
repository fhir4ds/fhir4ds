# Golden Standard - FP-09 FHIRPath String Search

1. FHIRPath string-search semantics must be spec-first: implementation behavior for `indexOf`, `substring`, `startsWith`, `endsWith`, and string-function `contains` must trace directly to HL7 FHIRPath §5.6.1-§5.6.5.
2. String positions and substring lengths must be measured in Unicode scalar-value characters, not UTF-8 bytes, host string storage units, or grapheme clusters.
3. Python fallback and native DuckDB/C++ public UDF surfaces must agree for all valid FP-09 expressions and for row-resilient handling of runtime type/cardinality errors.
4. Public result UDFs may convert evaluator errors to empty/NULL for row resilience, but `fhirpath_is_valid()` must remain an expression-validity signal rather than a sample-data success signal.
5. Static malformed calls, including wrong arity and literal wrong types, must be rejected consistently by native and fallback validity checks.
6. Dynamic argument expressions must be evaluated in the correct invocation focus, including sibling-field arguments and scoped calls inside `select()`.
7. Empty search terms must follow FP-09 function-specific semantics: `indexOf('')` returns `0`, while `startsWith('')`, `endsWith('')`, and `contains('')` return `true`.
8. `substring(start, length)` must distinguish out-of-range `start` from non-positive `length`: out-of-range `start` returns empty collection, while in-range `length <= 0` returns the empty string.
9. Fixes must be minimal and localized to the backend that is wrong; native C++ must not be touched when it already conforms and parity can be restored in Python fallback.
10. Focused tests must include both literal and resource-backed dynamic argument cases so host-language shortcut behavior cannot reappear.
