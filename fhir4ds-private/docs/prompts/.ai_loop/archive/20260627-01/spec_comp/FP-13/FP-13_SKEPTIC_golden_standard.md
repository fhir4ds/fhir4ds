# FP-13 Golden Standard - FHIRPath Equality

1. FHIRPath equality (`=`/`!=`) must return empty for indeterminate singleton
   comparisons, and `!=` must preserve that empty result rather than coercing it
   to true.
2. FHIRPath equivalence (`~`/`!~`) must be total for singleton values where the
   spec defines equivalence, and `!~` must be the Boolean converse of `~`.
3. Native DuckDB/C++ and Python fallback paths must agree for public DuckDB UDFs
   (`fhirpath`, `fhirpath_bool`, `fhirpath_json`) on all FP-13 equality and
   equivalence cases.
4. String equivalence must be Unicode-aware: case-insensitive comparison uses
   Unicode case behavior, and every Unicode White_Space code point normalizes to
   a normal space without collapsing runs or trimming endpoints.
5. String equality remains exact and must not inherit equivalence normalization.
6. Quantity equality must compare compatible units through semantic unit
   conversion, not string rendering.
7. Mixed calendar-vs-UCUM year/month duration equality is indeterminate because
   the calendar duration is variable; mixed week/day/hour/minute/second/
   millisecond duration equality uses definite unit conversion.
8. Quantity equivalence must remain broader than equality where the spec allows,
   including calendar-vs-UCUM year/month equivalence.
9. Date, DateTime, and Time equality must preserve precision semantics:
   precision mismatch returns empty for equality and false for equivalence.
10. Complex object/array equality and equivalence must recurse through child
    semantic equality/equivalence, including Decimal, Quantity, and String
    children.
11. Native evaluator changes must be reflected in the bundled
    `fhirpath.duckdb_extension` used by the Python package.
12. Regression coverage must include focused native/fallback parity, native
    sqllogictest coverage, and the full conformance baseline.
