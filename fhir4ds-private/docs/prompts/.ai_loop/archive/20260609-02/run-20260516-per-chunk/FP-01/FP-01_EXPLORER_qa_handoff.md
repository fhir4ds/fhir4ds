# QA Handoff - FP-01 EXPLORER

Scope: FHIRPath literal syntax and semantics for Boolean, String, Integer, Decimal, Date, Time, DateTime, Quantity, including time-valued quantities.

Spec checked: FHIRPath Normative Release section 4.1. In particular, section 4.1.2 says only listed string escapes are recognized, `\uXXXX` uses hexadecimal digits, and a backslash before a non-escape is ignored; its examples include a trailing backslash-before-delimiter case yielding the empty string. Section 4.1.6 disallows timezone offsets on Time literals. Section 4.1.7 requires DateTime offsets to use `(+|-)hh:mm` or `Z`. Section 4.1.8 defines calendar-duration quantity keywords.

Probe strategy: built `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp01_explorer_probe.py` and compared native C++ DuckDB registration, forced Python DuckDB fallback registration, and direct Python UDF wrappers across 137 literal edge cases. Cases included malformed decimals, lone Unicode surrogate escapes, trailing backslashes, partial temporal precisions, invalid timezone shapes, and calendar duration quantities.

Finding:
- `QA-001` MEDIUM: native C++ rejects a string literal whose final character before the delimiter is a backslash, while Python fallback follows the spec's ignored-backslash behavior. Reproducer expression: `'abc\'`. Native C++: `fhirpath_is_valid=false`, query raises `Invalid FHIRPath expression`. Forced Python fallback: `fhirpath_is_valid=true`, `fhirpath(...)` returns `['abc']`.

Non-findings:
- Invalid numeric forms such as `1e2`, `1.`, `.1`, and `1..2` are rejected by both backends, though exception classes differ.
- Invalid Time timezone forms such as `@T12Z` and invalid DateTime offset shapes such as `+09` are rejected or return empty depending on syntax-vs-semantic handling. No issue logged because they are not valid literals under section 4.1.
- Lone surrogate Unicode escapes (`\uD800`, `\uDC00`) remain questionable invalid-Unicode inputs. Both SQL surfaces fail rather than returning a normal scalar, but these are not Unicode characters; no autonomous fix logged for this chunk.
