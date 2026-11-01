# Golden Standard - CQL-11 HISTORIAN

Scope: CQL Arithmetic Operators Part 2 (`Maximum`, `Minimum`, `Modulo`, `Multiply`, `Negate`, `Precision`, `Predecessor`, `Power`, `Round`, `Subtract`, `Successor`, `Truncate`, `TruncatedDivide`) across translated SQL, native-loaded DuckDB registration, forced Python fallback registration, and C++-only/browser-style UDF/macro surfaces.

Golden behavior captured in this pass:

- Arithmetic Part 2 dynamic FHIR `value[x]` numeric operands use typed numeric extraction (`fhirpath_number`) for numeric-only operations such as `div`, `Power`/`^`, `Round`, and `Truncate`. Numeric choices such as `valueInteger` execute; nonnumeric choices such as `valueString` return NULL.
- CQL representational boundary rules are applied before SQL arithmetic can coerce or overflow: `-(minimum Integer)` and `-(minimum Long)` return NULL; `-(minimum Decimal)` returns the representable maximum Decimal; predecessor of minimum Decimal and successor of maximum Decimal return NULL.
- Static DateTime literal predecessor/successor underflow/overflow is rejected at translation time just like equivalent DateTime constructor boundaries.
- Public predecessor/successor helpers validate temporal strings before native C++ computation and return NULL for invalid inputs such as `T25:00`.
- Public `mathPower` returns NULL for unrepresentable results in both Python fallback and native C++ direct calls.
- `Precision(DateTime)` ignores timezone suffix digits, including negative offsets such as `-05:00`; the offset is not a precision component.
- `Round` negative ties continue to follow local official XML conformance (`Round(-0.5)` -> `0.0`) even though the published reference example differs.

Regression coverage added/maintained:

- Arithmetic Part 2 parity pytest covers translated SQL, native-loaded C++, forced Python fallback, C++-only/browser direct helpers, no-Python macro execution, boundary constants, and dynamic FHIR choice numeric paths.
- Native C++ CQL unittest covers direct helper behavior.
- Official CQL conformance remains 1706/1706.
- Full conformance remains 2822/2822 across ViewDefinition, FHIRPath, CQL, and DQM.
