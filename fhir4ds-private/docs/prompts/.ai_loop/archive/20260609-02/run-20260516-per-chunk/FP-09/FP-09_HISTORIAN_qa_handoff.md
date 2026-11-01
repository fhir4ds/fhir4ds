## QA Handoff - FP-09 HISTORIAN

Scope: FHIRPath Normative Release v2.0.0 §5.6.1-§5.6.5 string search functions: `indexOf`, `substring`, `startsWith`, `endsWith`, and `contains`.

Spec basis: §5.6 states these functions operate on collections with a single String item; more than one item or a non-String item signals an evaluation error. §5.6.1 returns a zero-based index or `-1`, with empty substring returning `0` and empty input/substring collection returning `{ }`. §5.6.2 returns the substring from a zero-based start, returns `{ }` when start lies outside the string, and treats empty length like omitted length. §5.6.3-§5.6.5 return Boolean string prefix/suffix/substring checks, with empty search string returning `true` and empty input returning `{ }`.

Fresh probes run:
- Native DuckDB extension vs forced Python fallback over 38 cases covering happy paths, empty input, empty argument collections, multi-item input, invalid argument/input types, `substring(start == length)`, empty length, and Unicode character positions (`a🙂bé`).
- Direct helper probes for `fhir4ds.fhirpath.duckdb.functions.string`.

Results:
- Public SQL UDFs: native extension loaded successfully and forced fallback registered successfully. All 38 native/fallback output tuples matched.
- Issue found: `QA-001` MEDIUM. The direct helper layer in `fhir4ds/fhirpath/duckdb/functions/string.py` still violates §5.6 semantics by coercing non-string singleton input through `str(value)` and by returning `['']` instead of `{ }` for `substring(start == len(input))`.

Suggested fix:
- Change `_get_singleton_string()` to raise `FHIRPathFunctionError` for non-string singleton input instead of coercing.
- Change helper `substring()` boundary check from `start > len(value)` to `start >= len(value)`.
- Update `fhir4ds/fhirpath/duckdb/tests/unit/test_string.py` to expect empty for start-at-end and errors for non-string input on the §5.6 helper functions.
