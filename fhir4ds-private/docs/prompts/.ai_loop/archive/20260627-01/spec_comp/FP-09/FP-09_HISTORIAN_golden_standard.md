# Golden Standard - FP-09 HISTORIAN

FHIRPath §5.6.1-§5.6.5 string-search behavior should satisfy these
architecture invariants across the Python fallback and native DuckDB/C++ paths.

1. `indexOf`, `substring`, `startsWith`, `endsWith`, and string-function
   `contains` share the same public semantics in native DuckDB/C++ and forced
   Python fallback registrations.
2. Search functions operate on singleton String input only. Empty input returns
   empty; multi-item or non-String input is an evaluation error that public
   DuckDB result UDFs materialize as row-resilient empty/NULL outputs.
3. Function arguments are ordinary FHIRPath expressions evaluated in the
   correct invocation focus. Sourced calls such as `s.indexOf(term)` must see
   sibling fields, and scoped calls such as `nested.select(s.contains(term))`
   must see the scoped item.
4. Static malformed signatures and literal argument type errors are expression
   validity failures and must make `fhirpath_is_valid()` false in both native
   and fallback paths.
5. Dynamic runtime type/cardinality errors are not expression-validity
   failures. They should keep `fhirpath_is_valid()` true while public result
   UDFs return empty/NULL.
6. String positions and substring lengths are measured in Unicode scalar
   values, not UTF-8 bytes or UTF-16 code units. Emoji/surrogate-pair and
   combining-mark inputs must stay parity-tested.
7. Empty String search terms are valid values: `indexOf('')` returns `0`, and
   `startsWith('')`, `endsWith('')`, and `.contains('')` return `true`.
8. `substring` start positions outside or equal to the string length return
   empty; zero or negative length returns the empty String.
9. The string `.contains(substring)` function remains distinct from the
   collection `contains` operator in parser validation and evaluator dispatch.
10. Native C++ changes to these paths require rebuilding/copying the bundled
    extension and validating native sqllogictest/unittest plus Python parity.
11. Review findings outside the chunk, such as delimited identifier surrogate
    handling and R4 type-specifier tables, should not be closed by FP-09
    evidence unless directly retested and remediated.
12. Loop state must remain file-authoritative: handoffs, archive entries,
    global knowledge, and `evolution.json` must describe the current fresh run,
    not archived artifacts.
