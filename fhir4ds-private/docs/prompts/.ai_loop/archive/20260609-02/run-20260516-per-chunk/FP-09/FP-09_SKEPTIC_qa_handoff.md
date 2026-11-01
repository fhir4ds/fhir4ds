# QA Handoff - FP-09 SKEPTIC

Scope: FHIRPath §5.6.1-§5.6.5 string search/manipulation: `indexOf`, `substring`, `startsWith`, `endsWith`, and string `contains`.

Spec basis verified against the HL7 FHIRPath Normative Release. The relevant clauses define 0-based character positions, empty-string search arguments returning `0`/`true`, empty input or empty argument collections returning empty, declared String/Integer parameter types, and singleton input error behavior. Public DuckDB wrappers are expected to convert those semantic errors to empty/NULL outside strict mode.

SKEPTIC hypotheses tested:
- Native C++ may coerce invalid argument types through `toString()`/`toNumber()`.
- Native C++ `contains()` may skip the input String type guard.
- Boundary `substring(start == length)` may differ across Python and native paths.
- UTF-8 indexes may be byte-based rather than character-based.
- Empty-string search arguments may be confused with empty collections.

Results:
- `QA-001` HIGH: native C++ DuckDB path coerces invalid string-search arguments and non-string `contains()` input. Examples: `s.indexOf(123) -> ['3']`, `s.endsWith(123) -> ['true']`, `s.contains(123) -> ['true']`, `s.substring('1') -> ['bc123']`, and `num.contains('2') -> ['true']`; forced Python fallback returns empty/NULL.
- `QA-002` MEDIUM: forced Python fallback returns `['']` for `s.substring(6)` on `"abcdef"` while native C++ returns empty/NULL. The spec example for `start == length` returns empty.

Clean areas observed:
- Empty-string arguments behave correctly in both paths for `indexOf('')`, `startsWith('')`, `endsWith('')`, and `contains('')`.
- UTF-8 character positions for `indexOf` and `substring` matched across native C++ and Python fallback in the tested cases.

Validation/probing run:
- Manual native C++ DuckDB SQL assertions through `register_fhirpath()` with `allow_unsigned_extensions`.
- Manual forced Python fallback SQL assertions by overriding `duckdb.__version__` before `register_fhirpath()`.

Recommended fix:
- Native C++: add singleton/type validation for String search arguments and Integer `substring` arguments, using `effectiveType()` instead of `toString()`/`toNumber()` coercion. Add an input String guard to `fn_contains_fn`.
- Python core: change `substring()` boundary from `start > len(string)` to `start >= len(string)`.
