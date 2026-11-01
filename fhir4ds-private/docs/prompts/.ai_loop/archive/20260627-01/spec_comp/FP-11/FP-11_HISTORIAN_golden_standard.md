# Golden Standard - FP-11 HISTORIAN

1. FHIRPath Math functions must implement the current HL7 §5.7 signatures and
   must reject incompatible inputs instead of coercing through strings or broad
   numeric truthiness.
2. Native C++ and forced Python fallback DuckDB registrations must agree on
   public `fhirpath*` UDF results for every §5.7 function where both paths exist.
3. Quantity-capable math functions (`abs`, `ceiling`, `floor`, `round`,
   `truncate`) must preserve Quantity units for literals and resource-backed
   FHIR Quantity JSON.
4. Numeric-only math functions (`exp`, `ln`, `log`, `power`, `sqrt`) must not
   accept Quantity, String, Boolean, or structural JSON as numeric evidence.
5. Integer and Long boundary handling must not pass through binary floating
   point when the specified result is an integral value.
6. Decimal-shaped math results, especially `power()` and `round()`, must remain
   visible as Decimal through `type()`, `is Decimal`, text, and JSON surfaces.
7. Public result UDFs may convert row-level semantic errors to empty/NULL for
   analytics resilience, but `fhirpath_is_valid()` must still represent
   expression validity rather than sample data success.
8. FHIR Quantity materialization should reuse shared parsing/type helpers rather
   than duplicate ad hoc dict recognition in individual math functions.
9. Native source changes must be rebuilt and the bundled
   `fhirpath.duckdb_extension` copied before validating Python package behavior.
10. Regression coverage for native evaluator changes must include focused
    Python parity tests, native sqllogictest assertions, the fresh QA probe, and
    the full conformance gate.
