# Golden Standard - FP-12 Tree Navigation and Utility Functions

Scope: FHIRPath §5.8 `children()` / `descendants()` and §5.9
`trace(name, [projection])`, `now()`, `timeOfDay()`, and `today()` across the
Python evaluator, DuckDB Python fallback UDFs, and native C++ DuckDB extension.

Invariants:

1. `children()` must return immediate child nodes of every input item, skip
   `resourceType`, hide split primitive extension containers, and preserve JSON
   null child nodes at this function boundary.
2. `descendants()` must be behaviorally equivalent to `repeat(children())`,
   excluding the input items themselves and using semantic duplicate detection
   rather than a fixed-depth traversal.
3. Tree navigation results have undefined order; tests must compare stable
   counts, membership, or JSON surfaces and avoid order-dependent assertions
   unless the assertion is explicitly about current implementation parity.
4. `trace(name)` must validate that `name` is a singleton String evaluated
   before projection execution and must return the original input collection.
5. `trace(name, projection)` must evaluate `projection` as a scoped function
   once per input item with `$this` and `$index`, while diagnostic projection
   values must not replace the returned input collection.
6. Scoped function evaluation must restore `$index`, transient variables, and
   chain-defined variables after the function returns or raises.
7. `children()`, `descendants()`, `now()`, `today()`, and `timeOfDay()` are
   exact zero-argument functions; `trace()` accepts exactly one or two
   arguments.
8. Public DuckDB result UDFs must remain row-resilient for invalid signatures:
   invalid expressions return empty/NULL public results while
   `fhirpath_is_valid()` reports false.
9. `now()`, `today()`, and `timeOfDay()` must be deterministic within a single
   expression evaluation, even if evaluated multiple times after expensive
   intermediate work.
10. Native C++ and forced Python fallback DuckDB paths must agree on validity,
    public result shape, and row resilience for every FP-12 behavior where both
    paths exist.
11. Native evaluator changes must be accompanied by sqllogictest coverage and a
    rebuilt/copied bundled `fhirpath.duckdb_extension`.
12. Fresh QA/architect probes must pin `sys.path` to the workspace root when
    launched from `.temp/qa` or `.temp/architect`, so they validate the current
    source tree rather than any installed package.
