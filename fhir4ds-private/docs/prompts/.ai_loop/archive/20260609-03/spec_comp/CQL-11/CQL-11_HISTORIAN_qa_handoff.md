# QA Handoff - CQL-11 HISTORIAN

## Scope

- Chunk: CQL-11, Arithmetic Operators Part 2.
- Personality: HISTORIAN.
- Spec anchor: CQL Reference v1.5.3 Appendix B, Arithmetic Operators, especially Round, Maximum/Minimum, Modulo, Multiply, Negate, Precision, Predecessor, Power, Subtract, Successor, Truncate, and Truncated Divide.

## Fresh Probe

- Created `.temp/qa/cql11_historian_probe.py`.
- Exercised forced Python fallback, native-loaded registration, no-Python extension runtime, and translated CQL execution.
- Included regression coverage for CQL-11 SKEPTIC predecessor/successor Quantity shape, malformed Quantity JSON rejection, temporal precision stepping, numeric precision preservation, Quantity modulo/division, dynamic math functions, and negative rounding.

## Finding

- `QA-001` HIGH: `Round` / `RoundTo` / `mathRound` round negative half values toward positive infinity.
- Evidence:
  - `Round(-0.5)` returned `0.00000000`; expected `-1.00000000`.
  - `Round(-1.5)` returned `-1.00000000`; expected `-2.00000000`.
  - `RoundTo(-2.55, 1)` returned `-2.50000000`; expected `-2.60000000`.
  - Reproduced on forced Python fallback, native-loaded registration, and no-Python extension.
- Spec basis: the official CQL Round text defines traditional rounding and explicitly says values less than or equal to `-0.5` and greater than `-1.0` round to `-1`.
- `QA-002` HIGH: `Round` null precision does not default to zero across public surfaces.
- Evidence:
  - `RoundTo(3.1, NULL)` returned `NULL` through the direct SQL macro.
  - `mathRound('3.1', NULL)` returned `NULL` in native C++ while Python fallback returned `3`.
- Spec basis: the official CQL Round text says that if precision is not specified or is null, precision `0` is assumed.

## Notes For Fix

- Patch all public surfaces together:
  - Python `mathRound` in `fhir4ds/cql/duckdb/udf/math.py`.
  - SQL macros `Round` / `RoundTo` in `fhir4ds/cql/duckdb/macros/math.py`.
  - C++ no-Python `MathRoundFunc` in `extensions/cql/src/cql_extension.cpp`.
- Add focused parity assertions to `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py` and the no-Python WASM surface tests.
