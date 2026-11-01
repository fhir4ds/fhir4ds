# QA Handoff - FP-10 HISTORIAN

Scope: FHIRPath section 5.6.6-5.6.12 string transform functions: `upper()`, `lower()`, `replace()`, `matches()`, `replaceMatches()`, `length()`, and `toChars()`.

Spec basis: the official FHIRPath string transform section defines `upper()` and `lower()` as converting all characters in the singleton input string to upper/lower case; empty input returns empty and multi-item input signals an error. `replace()`, `matches()`, `replaceMatches()`, `length()`, and `toChars()` are likewise singleton string operations, with declared string arguments where applicable.

Fresh QA work performed:
- Read the active source paths for Python core, direct DuckDB helpers, native C++ evaluator, current parity tests, and official R4 conformance examples.
- Compared native C++ DuckDB behavior against forced Python fallback behavior using public UDFs.
- Probed Unicode case transforms, empty-pattern replacement, regex capture substitution, invalid input types, code-point `length()`, and `toChars()` on supplementary-plane characters.

Finding:
- `QA-001` MEDIUM SPEC_VIOLATION: native C++ `upper()` did not match Python fallback Unicode case behavior for German sharp s and Greek final sigma. Reproducer: `fhirpath_text({"s":"Straße"}, "s.upper()")` returned `STRAßE` natively but `STRASSE` in fallback; `fhirpath_text({"s":"Σςσ"}, "s.upper()")` returned `ΣϢΣ` natively but `ΣΣΣ` in fallback. The final sigma path produced U+03A2, an unassigned code point, because the generic Greek lowercase range check ran before the final-sigma special case.

No additional issue was logged for PCRE named capture syntax in `replaceMatches()`: the spec notes platform regex dialect variation, and numeric capture substitution already works consistently across native and fallback paths.
