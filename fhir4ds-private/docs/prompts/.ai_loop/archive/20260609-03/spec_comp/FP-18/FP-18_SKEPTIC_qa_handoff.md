# QA Handoff: FP-18 SKEPTIC

Scope: FHIRPath §6.6 Math Operations and §6.7 Date/Time Arithmetic across DuckDB native C++ and forced Python fallback public UDF surfaces.

Spec checked: FHIRPath Normative Release v2.0.0 §6.6 requires math operands to be single elements and signals an error for multi-item operands. §6.7 defines date/time arithmetic with precision-aware truncation of more precise quantities; official R4 fixtures include `testPlusDate19`, where `@1973-12-25T00:00:00.000+10:00 + 0.1 's'` remains `@1973-12-25T00:00:00.000+10:00`, and `testPlusDate20`, where `10 'ms'` applies sub-second arithmetic.

Hypotheses tested:
- Numeric promotion and divide-by-zero could diverge between native and fallback.
- Negative `div`/`mod` could leak host-language floor or binary floating artifacts.
- `+` string concatenation and `&` empty-as-empty-string behavior could be conflated.
- Quantity operations could silently ignore incompatible units.
- Date/Time partial precision and second-vs-millisecond arithmetic could truncate incorrectly.
- Constant multi-item math operands could be row-resilient at runtime but incorrectly marked valid by `fhirpath_is_valid()`.

Fresh probe:
- Added `.temp/qa/fp18_skeptic_probe.py`.
- Covered 21 expressions across `fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_number`, and `fhirpath_is_valid` on native C++ and forced Python fallback.

Findings:
- `QA-001` HIGH CONFIRMED: temporal second/millisecond arithmetic needed native/fallback parity hardening. The initial fractional-second expectation was corrected against official R4 `testPlusDate19`: `0.5 seconds` is truncated to `0 seconds`, while `500 milliseconds` applies sub-second arithmetic. Final regression expectations now assert that native and fallback both preserve `@T00:00:00.500 + 0.5 seconds`, `@2016-01-01T00:00:00.500 + 0.5 seconds`, and resource-backed equivalents, while still applying millisecond quantities.
- `QA-002` MEDIUM OPEN: forced Python fallback `fhirpath_is_valid('(1 | 2) + 1')` returns true, while native returns false. The expression is constant-invalid under §6.6 singleton math operand rules.

No source files were modified during QA. Proceed to remediation.
