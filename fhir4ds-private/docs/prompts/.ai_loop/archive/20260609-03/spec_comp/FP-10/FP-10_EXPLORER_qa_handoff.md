# QA Handoff: FP-10 EXPLORER

## Scope

- Chunk: FP-10, FHIRPath §5.6.6-§5.6.12 string transforms.
- Personality: EXPLORER.
- Spec source: HL7 FHIRPath Normative Release §5.6.6-§5.6.12.
- Required surfaces: native DuckDB C++ extension and forced Python fallback.

## Spec Grounding

FHIRPath §5.6 states string manipulation functions operate on singleton String inputs and error for multi-item or non-String input. §5.6.6 and §5.6.7 require `upper()` and `lower()` to convert all characters in the input string to upper/lower case. §5.6.8-§5.6.12 define empty propagation for `replace`, `matches`, `replaceMatches`, `length`, and `toChars`.

## Probe

Created and ran `.temp/qa/fp10_explorer_probe.py`.

Coverage included:
- Chained transforms and empty-string vs empty-collection cases.
- Dynamic argument focus through sibling fields and `select()`/`where()`.
- Regex ReDoS guard boundaries, malformed literal regex, and dynamic invalid regex row resilience.
- Replacement capture groups and empty substitutions.
- UTF-8 regex dot, `length()`, and `toChars()` over accented text, emoji, and combining marks.
- Invalid arity, non-string runtime inputs, and static non-string literals.
- Extra Unicode case pairs outside prior FP-10 coverage.

Result:
- Cases: 47.
- Expected-output failures: 0.
- Native/fallback mismatches: 4, all same root cause.

## Finding

`QA-001` MEDIUM: native `upper()`/`lower()` misses common Unicode case pairs that the forced Python fallback handles:
- `turkish_upper.lower()` native `İstanbul`, fallback `i̇stanbul`.
- `turkish_lower.upper()` native `ıSTANBUL`, fallback `ISTANBUL`.
- `greek_accent_lower.upper()` native `άέήίόύώ`, fallback `ΆΈΉΊΌΎΏ`.
- `greek_accent_upper.lower()` native `ΆΈΉΊΌΎΏ`, fallback `άέήίόύώ`.

## Handoff

Fix the native C++ case-mapping table in `extensions/fhirpath/src/fhirpath/evaluator.cpp`, add parity tests for these EXPLORER Unicode cases, rebuild/copy the bundled extension, and rerun the probe plus focused FP-10 parity tests.
