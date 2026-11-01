# Golden Standard - CQL-11 EXPLORER

Scope: CQL Arithmetic Operators Part 2 public and translated behavior for `Maximum`, `Minimum`, `Modulo`, `Multiply`, `Negate`, `Precision`, `Predecessor`, `Power`, `Round`, `Subtract`, `Successor`, `Truncate`, and `TruncatedDivide`.

Golden behavior captured in this pass:

- Direct public SQL macros are part of the CQL surface. `Div(x, y)` implements CQL truncated divide with truncation toward zero and NULL on zero divisor, including Decimal operands.
- `minimum DateTime` and `maximum DateTime` retain the official XML UTC boundary suffix (`Z`).
- Direct public predecessor/successor helpers return NULL at Decimal representational min/max boundaries in Python fallback, native-loaded C++, and C++-only/no-Python surfaces.
- Predecessor/successor over Date, DateTime, and Time values step by the lowest specified precision and preserve lexical precision. Examples: `2014` steps by years, `2014-01` by months, `2014-01-01T10` by hours, and `T12:30` by minutes.
- Partial DateTime marker values such as `2014T`, `2014-01T`, and `2014-01-01T` are DateTime values and should not be routed through Decimal or rejected as malformed.
- Mixed scalar/Quantity `mod` and `div` must not emit `parse_quantity(<number>)`; scalar operands are converted to unit `1` Quantity JSON before Quantity UDF dispatch, with incompatible units returning NULL.

Regression coverage added/maintained:

- Arithmetic Part 2 parity pytest covers translated SQL, native-loaded C++, forced Python fallback, C++-only/browser direct helpers, Decimal direct `Div`, DateTime max/min constants, Decimal boundary helpers, partial-precision predecessor/successor, and mixed scalar/Quantity modulo/divide.
- Native C++ CQL unittest covers direct helper registration and extension loading.
- Official CQL conformance remains 1706/1706.
- Full conformance remains 2822/2822 across ViewDefinition, FHIRPath, CQL, and DQM.
