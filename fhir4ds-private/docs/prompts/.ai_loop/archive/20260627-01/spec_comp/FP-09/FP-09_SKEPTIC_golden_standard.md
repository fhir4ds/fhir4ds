# FP-09 Golden Standard - FHIRPath String Search

Scope: FHIRPath §5.6.1-§5.6.5 String Manipulation (Search) across Python
fallback, native DuckDB/C++, and public DuckDB UDF wrappers.

## Invariants

1. `indexOf(substring)`, `substring(start[, length])`, `startsWith(prefix)`,
   `endsWith(suffix)`, and string-function `contains(substring)` are singleton
   String input functions; multi-item input or wrong runtime type must not be
   coerced through host-language stringification.
2. Required argument expressions are ordinary FHIRPath expressions. For
   sourced calls like `s.indexOf(term)` and `s.substring(start, length)`,
   dynamic arguments must resolve in the outer invocation focus, including
   scoped contexts.
3. Empty required argument collections propagate empty. An omitted optional
   `substring` length is distinct from an explicitly empty length; explicit
   empty length behaves as omitted per §5.6.2.
4. String positions and lengths are measured in Unicode scalar values, not
   UTF-8 bytes, UTF-16 code units, or grapheme clusters.
5. `indexOf('')` returns `0`; `startsWith('')`, `endsWith('')`, and
   `contains('')` return `true`; empty input collections still return empty.
6. `substring()` returns empty when `start < 0` or `start >= length(input)`;
   zero or negative non-empty `length` returns the empty string.
7. String-function `contains(substring)` must remain distinct from the
   collection `contains` operator in parsing, validation, and public UDF
   behavior.
8. Public DuckDB result UDFs must be row-resilient: evaluator semantic errors
   return empty/NULL outputs rather than aborting the query.
9. `fhirpath_is_valid()` validates expression form, not the evaluation outcome
   against a specific resource. Dynamic runtime type errors may keep validity
   true, while static malformed signatures and literal wrong-type arguments
   may be invalid.
10. Native/C++ and forced Python fallback registrations must agree on public
    outputs for list, text, JSON, Boolean, number, and validity surfaces.
11. Focused regression coverage belongs in a parity test near the FHIRPath
    DuckDB integration tests and, after native edits, in the native
    sqllogictest/unittest plus bundled extension freshness checks.
12. Remaining milestone review findings outside this chunk must not be treated
    as FP-09 evidence unless they affect these string-search functions.
