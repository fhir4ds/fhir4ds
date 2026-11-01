# FP-12 HISTORIAN Golden Standard

Scope: FHIRPath §5.8 Tree Navigation and §5.9 Utility Functions in the Python
fallback engine and native DuckDB/C++ extension.

1. `children()` must project the immediate logical child nodes of each input
   item without surfacing implementation-only FHIR JSON split primitive
   containers such as `_birthDate`.
2. `children()` and `descendants()` must preserve JSON null child nodes as
   present items; ordinary member navigation may skip nulls, but tree
   navigation exposes nodes.
3. `descendants()` must be behaviorally equivalent to `repeat(children())`:
   exclude the input items, traverse recursively without fixed shallow-depth
   cutoffs, and avoid revisiting equal values using FHIRPath equality-compatible
   keys.
4. Tree-navigation result order is undefined by the spec; tests and production
   logic must not depend on `first()`, `last()`, `skip()`, or `take()` over
   `children()`/`descendants()` output.
5. Function dispatch must enforce exact public signatures for `children()`,
   `descendants()`, `now()`, `today()`, `timeOfDay()`, and one-or-two argument
   `trace(name, [projection])` before data sparsity can hide malformed calls.
6. `trace(name)` is an identity function over the input collection. It may
   emit diagnostics, but the returned collection must be exactly the original
   input.
7. `trace(name, projection)` must evaluate `name` once in the outer invocation
   focus, then evaluate `projection` once per input item with scoped `$this` and
   `$index`, flatten the diagnostic projection, return the original input, and
   restore all surrounding evaluator scope.
8. Runtime errors inside a trace projection must remain row-resilient at public
   DuckDB UDF boundaries: result UDFs return empty/NULL while static expression
   validity remains true when the expression shape is otherwise valid.
9. `now()`, `today()`, and `timeOfDay()` must be deterministic within one
   expression evaluation. Repeated calls in a single expression return the same
   value for each helper.
10. Current-time helper timestamp source and precision may differ between native
    and Python fallback registrations, but each helper must return the correct
    FHIRPath type shape and must be internally deterministic.
11. Native and forced Python fallback DuckDB registrations must be parity-tested
    for every FP-12 public behavior where both paths exist.
12. Native evaluator changes touching FP-12 dispatch must rebuild and copy the
    bundled `fhirpath.duckdb_extension`, and focused parity tests must be kept
    alongside native sqllogictest coverage.
