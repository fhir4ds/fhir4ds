## Golden Standard - CQL-11 Arithmetic Operators Part 2

1. Public CQL DuckDB helpers are compatibility surfaces, not private implementation details; native-loaded registration, forced Python fallback, and C++-only/browser-style registration must agree where the function or macro exists.
2. SQL macros used by translated CQL must also be valid in no-Python runtimes; macro parity needs direct tests after registration, not only translator execution tests.
3. Numeric helper UDFs must return SQL NULL for invalid domains, NaN, infinity, and unrepresentable outputs rather than surfacing backend-specific strings or exceptions.
4. `Round` semantics are CQL semantics, not host-language banker rounding or away-from-zero rounding; tie behavior is consistent for positive and negative inputs.
5. Quantity arithmetic must normalize compatible UCUM units through the shared quantity conversion path before modulo/truncated divide, and output must preserve the left operand unit.
6. Translator lowering must preserve CQL static-invalid cases when the spec says the expression cannot be represented, even when public SQL helper wrappers use NULL for row-level resilience.
7. Temporal boundary constants must retain their lexical precision and CQL type identity, including `T` markers and millisecond precision for DateTime and Time.
8. C++ UDFs must materialize owned values before freeing parsed JSON or temporal buffers, and all boundary failures should set DuckDB result NULL instead of throwing from direct helper calls.
9. Native C++ source edits require rebuilding and copying the bundled extension before Python tests that load the packaged extension can be trusted.
10. Regression validation for this surface requires focused parity tests, native C++ SQL tests, official conformance, and the full `fhir4ds` pytest suite.
