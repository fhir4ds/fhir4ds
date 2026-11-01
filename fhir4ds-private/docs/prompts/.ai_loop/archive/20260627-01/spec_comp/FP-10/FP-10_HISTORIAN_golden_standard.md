# Golden Standard - FP-10 HISTORIAN

Date: 2026-06-12

Scope: FHIRPath §5.6.6-§5.6.12 String Manipulation (Transform) across the
Python fallback and native DuckDB/C++ extension.

## Invariants

1. Public FHIRPath behavior must be spec-grounded at function boundaries:
   signatures, empty-input behavior, singleton errors, and result types must
   match the active HL7 FHIRPath section.
2. Native DuckDB/C++ and forced Python fallback paths must agree for the same
   public UDF surfaces whenever both paths implement the function.
3. UTF-8 string operations must operate on Unicode scalar values, not bytes;
   this applies to `replace('', ...)`, regex `.` normalization, `length()`,
   `toChars()`, and case conversion loops.
4. Unicode behavior should be delegated to established Unicode data/libraries
   where available rather than maintained as incomplete ad hoc ranges.
5. Any unavoidable native Unicode special-case tables must be data-only,
   narrowly scoped, and covered by native/fallback parity tests.
6. Regex transform behavior must preserve current `matches()` search semantics
   and optional `i`/`m` flag validation for both `matches()` and
   `replaceMatches()`.
7. Public result UDFs must remain row-resilient for invalid expressions or
   runtime type errors: result wrappers return empty/NULL and
   `fhirpath_is_valid()` carries validity where applicable.
8. Dynamic function arguments in sourced calls must evaluate against the outer
   invocation focus, not the already extracted source string.
9. Native changes require rebuilding and copying the bundled extension, and
   the build, repository, and package extension hashes must match.
10. Focused tests must cover the permanent regression path, not only the
    temporary probe; native sqllogictests and Python integration parity should
    move together.
