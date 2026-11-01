# CQL-08 SKEPTIC Engineer Handoff

## Implemented Changes

- `fhir4ds/cql/translator/expressions/_functions.py`
  - Added nullological functions to the static-source inlining path so static
    definition aliases do not lower to patient-correlated CTE lookups.
- `fhir4ds/cql/translator/expressions/_lists.py`
  - Inlined safe static list elements during SQL array generation.
- `fhir4ds/cql/duckdb/macros/logical.py`
  - Tightened `IsTrue` and `IsFalse` to return true only for actual Boolean
    true/false values.
  - Removed the too-narrow two-argument `Coalesce` macro.
- `fhir4ds/cql/duckdb/udf/logical.py`
  - Added public variadic `Coalesce(*args)` with `VARIANT` return type for
    scalar variadic and single-list overloads.
  - Made legacy `logicalCoalesce` serialize JSON object/list values compactly.
- `fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py`
  - Added native-loaded vs forced Python fallback coverage for static aliases,
    non-Boolean `IsTrue`/`IsFalse`, legacy JSON-object `logicalCoalesce`, and
    variadic/list/date `Coalesce` direct SQL calls.
- `fhir4ds/cql/duckdb/macros/__init__.py`
  - Updated macro registration documentation to reflect that `Coalesce` is a
    UDF, not a macro.

## Notes for Next Personality

- Translated CQL still lowers normal `Coalesce(...)` expressions to SQL
  `COALESCE(...)` where appropriate. The new public UDF is for the direct
  quoted DuckDB CQL function surface and for overloads a single macro cannot
  represent.
- The C++ extension was not changed in this pass. Native-loaded parity was
  tested through the bundled extension plus Python supplements, which is the
  public registered surface for this chunk.

