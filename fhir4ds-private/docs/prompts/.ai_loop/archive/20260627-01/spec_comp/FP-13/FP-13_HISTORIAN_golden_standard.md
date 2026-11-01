# FP-13 HISTORIAN Golden Standard

Scope: FHIRPath §6.1 equality and equivalence in the Python fallback engine,
DuckDB UDF wrapper, and native C++ DuckDB extension.

## Invariants

1. Equality and equivalence must be semantic operations, not string rendering
   comparisons; Quantity, Date/Time, numeric, String, and complex values each
   use their spec-specific comparison semantics.
2. Python fallback and native C++ must expose the same public results through
   `fhirpath`, `fhirpath_json`, `fhirpath_bool`, and `fhirpath_text` wherever
   both backends exist.
3. Resource-backed FHIR JSON Quantity values must be materialized into the same
   semantic Quantity shape as FHIRPath Quantity literals before comparison.
4. Numeric primitives compared with Quantity values must be coerced only through
   the §6.1 implicit unit `1` conversion; other cross-type equality remains
   empty/NULL when not explicitly convertible.
5. Quantity unit conversion must be centralized through canonical UCUM/base-unit
   conversion helpers. Local subsets must not drift from shared Quantity
   conversion data.
6. Quantity equality and equivalence must preserve tri-state behavior: true,
   false, or empty/NULL when unit conversion is empty or precision is
   indeterminate.
7. Quantity equivalence must distinguish truly non-commensurable dimensions
   such as length versus time from supported commensurable UCUM conversions
   such as pound versus kilogram.
8. Date/DateTime/Time equality must preserve precision-sensitive empty results,
   while Date/Time equivalence may return false on precision/type mismatch as
   required by §6.1.
9. String equivalence must use Unicode-aware case and whitespace normalization
   without collapsing runs or trimming; exact string equality must remain exact.
10. Multi-item and complex-object equality/equivalence must recurse through the
    same singleton semantic comparison functions instead of parallel ad hoc
    ordering or stringification logic.
11. Native extension source, built extension artifact, Python bundled extension,
    and native sqllogictest expectations must move together after C++ changes.
12. Official conformance and focused parity tests must cover native-loaded
    DuckDB, forced Python fallback DuckDB, direct Python fallback, and the R4
    conformance sentinel where one exists.
