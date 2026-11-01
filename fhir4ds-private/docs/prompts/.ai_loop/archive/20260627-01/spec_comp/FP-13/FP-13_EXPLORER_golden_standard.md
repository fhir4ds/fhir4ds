# FP-13 EXPLORER Golden Standard

Scope: FHIRPath §6.1 equality/equivalence across the Python fallback engine,
DuckDB UDF wrappers, and native C++ DuckDB extension.

## Invariants

1. `=`, `!=`, `~`, and `!~` are semantic operators; they must not compare via
   rendered strings except for exact string values.
2. Native C++ and forced Python fallback DuckDB registrations must produce the
   same public `fhirpath`, `fhirpath_text`, `fhirpath_json`, and
   `fhirpath_bool` results for supported §6.1 expressions.
3. Direct Python fallback UDF helpers must match the forced DuckDB fallback for
   the same expression/resource pairs.
4. Quantity equality and equivalence must use shared unit-conversion semantics,
   preserve empty/NULL for non-commensurable units, and keep calendar-vs-UCUM
   year/month equality indeterminate.
5. Quantity equivalence must evaluate converted values using precision derived
   from the original operands, not precision accidentally introduced by base
   unit conversion.
6. Numeric primitives compare with Quantity values only through the §6.1
   implicit unit `1` conversion; arbitrary cross-type equality remains empty.
7. Date, DateTime, and Time equality must preserve precision-sensitive empty
   results; equivalence may return false for precision mismatch as specified.
8. String equivalence must normalize Unicode whitespace one-for-one and ignore
   case without trimming or collapsing whitespace runs.
9. Complex-object and multi-item equality/equivalence must recurse through the
   same singleton semantic comparison rules used by direct child comparisons.
10. Native JSON numeric equality/equivalence must preserve exact JSON number
    text for Integer/Long-sized values and must not collapse distinct values
    through binary floating-point conversion.
11. `fpValuesEqual()` and the operator-local equality/equivalence helpers must
    stay aligned because collection/set helpers and direct operators share the
    same semantic contract.
12. Any C++ equality change must move with native sqllogictest coverage, a
    rebuilt package-bundled `fhirpath.duckdb_extension`, hash verification, and
    focused native/fallback parity tests.
