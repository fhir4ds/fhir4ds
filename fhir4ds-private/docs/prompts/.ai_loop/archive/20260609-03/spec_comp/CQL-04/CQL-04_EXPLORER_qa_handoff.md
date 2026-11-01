# QA Handoff - CQL-04 EXPLORER

Scope: CQL logical operators `And`, `Implies`, `Not`, `Or`, and `Xor` with
EXPLORER emphasis on recombined edge cases after SKEPTIC/HISTORIAN.

Spec basis: CQL 1.5.3 Appendix B defines logical operators as Boolean-only
operators with three-valued truth tables. `and`, `or`, `xor`, and `implies`
take Boolean left/right operands, and `not` takes one Boolean operand.

Fresh probe: `.temp/qa/cql04_explorer_probe.py`.

Coverage:
- Direct public helper parity across forced Python fallback, native-loaded
  registration, and no-Python C++ plus pure SQL macros for Boolean truth
  tables and invalid numeric/string/list operands.
- Translated CQL validation for nested `as Any`, `convert ... to Any`,
  conversion functions, clinical values, tuples, intervals, `between`, and
  precedence chains.
- Patient-context population SQL over Boolean runtime parameters on both
  forced Python fallback and native-loaded registrations.

Finding:
- `QA-001` HIGH `SPEC_VIOLATION`: static logical operand inference allowed
  non-Boolean values to reach raw SQL logical operators when the operand shape
  was `convert 1 to Any`, `convert true to String`, `ToString(true)`,
  `ToString(true) as Any`, `ToInteger('1')`, or `ToQuantity(...)`. DuckDB then
  coerced some of those values in `AND`/`OR` expressions instead of enforcing
  CQL Boolean-only operands.

Validation run before handoff:
- `python3 .temp/qa/cql04_explorer_probe.py`: passed after remediation.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py -q`: 28 passed after remediation.
- Focused broader parity with primitive parameter/type tests: 39 passed after remediation.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
