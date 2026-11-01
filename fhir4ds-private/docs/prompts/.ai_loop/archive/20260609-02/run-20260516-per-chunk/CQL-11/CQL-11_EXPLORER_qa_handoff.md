# QA Handoff - CQL-11 EXPLORER

Scope: independent exploratory CQL Arithmetic Operators Part 2 audit over direct helper SQL, translated CQL, native-loaded DuckDB, forced Python fallback, and C++-only/no-Python registration.

Confirmed five findings:

- Direct public `Div(x, y)` macro used DuckDB `//`, which returned fractional division for Decimal inputs such as `Div(10.1, 3.1)` instead of CQL truncated divide.
- `minimum DateTime` and `maximum DateTime` translated without the official XML `Z` suffix.
- Direct public `predecessorOf`/`successorOf` still stepped Decimal min/max strings outside CQL representational bounds.
- Partial-precision predecessor/successor used the wrong step or diverged across backends: year dates were treated as numeric in Python/native-loaded paths, year-month dates failed, C++-only month dates lost the month step, and partial Time/DateTime stepped by milliseconds/seconds instead of the lowest specified precision.
- Mixed scalar/Quantity `mod` and `div` lowered scalar operands through `parse_quantity(<number>)`, producing DuckDB binder errors instead of row-resilient Quantity/null behavior.

The sidecar explorer independently confirmed the first three findings without reading workflow archive output.
