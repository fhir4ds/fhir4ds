# Engineer Handoff: CQL-11 SKEPTIC

Resolved two HIGH CQL Arithmetic Part 2 issues from the fresh SKEPTIC probe.

Spec basis: CQL Logical Specification v1.5.3 arithmetic operators. Quantity predecessor/successor add or subtract 1 for integer-authored Quantity values, add or subtract `1e-8` for decimal-authored Quantity values, return null when the operation cannot be represented, and malformed Quantity shapes must remain row-resilient at public SQL helper boundaries.

Fixes implemented:
- Preserved integer Quantity literal shape in the parser and translator so `1 'cm'` emits JSON value `1`, while `1.0 'cm'` emits `1.0`.
- Routed translated `predecessor of <Quantity literal>` and `successor of <Quantity literal>` to raw Quantity JSON instead of `parse_quantity(...)`, which can normalize integer spelling on native-loaded C++ registration.
- Hardened Python `predecessorOf` / `successorOf` Quantity JSON handling to require a raw JSON numeric value token and strict Quantity parser validation before stepping. Numeric-string values now return SQL NULL.
- Hardened the no-Python C++ `predecessorOf` / `successorOf` Quantity path to use step `1` for integer-authored Quantity values and `1e-8` for decimal/exponent-authored values.
- Rebuilt `extensions/cql/build/release/extension/cql/cql.duckdb_extension` and copied it to `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.

Validation passed:
- Fresh probe: `.temp/qa/cql11_skeptic_probe.py`
- Focused CQL-11 parity: `test_arithmetic_part2_parity.py` 7/7
- Adjacent arithmetic/no-Python surface: 12/12
- Full conformance: 2822/2822

Changed code/tests:
- `fhir4ds/cql/parser/ast_nodes.py`
- `fhir4ds/cql/parser/parser.py`
- `fhir4ds/cql/translator/expressions/_core.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/udf/math.py`
- `extensions/cql/src/cql/boundary.cpp`
- `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
- `extensions/cql/AGENTS.md`
- `AGENTS.md`
