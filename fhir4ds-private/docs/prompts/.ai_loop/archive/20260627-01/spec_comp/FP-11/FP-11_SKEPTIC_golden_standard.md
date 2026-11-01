# FP-11 Golden Standard - FHIRPath Math

1. FHIRPath math semantics must be grounded in the current HL7 FHIRPath §5.7 text, not in older local parity expectations.
2. Native C++ DuckDB UDF behavior and forced Python fallback behavior must match for public `fhirpath*` UDF outputs and `fhirpath_is_valid()`.
3. Quantity-capable math functions must preserve units without converting through display strings or JSON text.
4. Numeric-only math functions must reject Quantity and other non-numeric values through typed evaluator errors that public UDFs convert to empty/NULL.
5. Function arity and singleton validation must be enforced before implementation-specific coercions.
6. Argument expressions such as `log(base)`, `power(exponent)`, and `round(precision)` must evaluate in the documented outer invocation focus.
7. Result type metadata must remain observable through `type()`, `is`, and public JSON/text UDF surfaces.
8. Direct helper APIs that advertise FHIRPath math semantics should not preserve behavior that contradicts the main evaluator.
9. Native source, release build output, repository extension copy, and Python package bundled extension must stay synchronized after C++ edits.
10. Regression coverage must include native C++, forced Python fallback, direct helper tests where applicable, and the official conformance baseline.
