# QA Handoff - CQL-04 HISTORIAN

## Scope
- Fresh HISTORIAN audit of CQL logical operators: `And`, `Implies`, `Not`, `Or`, `Xor`.
- Did not inspect archived `spec_comp/**` outputs.

## Spec Basis
- CQL 1.5.3 Appendix B logical operators define three-valued truth tables for `and`, `implies`, `not`, `or`, and `xor`.
- CQL 1.5.3 Developer's Guide Table 3-F defines precedence: `and` above `or`/`xor`, and `implies` below disjunction; operators in the same category associate left-to-right.

## Probes
- Compared direct DuckDB macros/UDFs on native-loaded and forced Python fallback registrations for all true/false/null combinations.
- Executed translated scalar definitions covering precedence, associativity, parenthesized overrides, and temporal precision expressions followed by logical chains.
- Probed query `let`/`where`/`return` logical expressions through generated population SQL with FHIR resources on both DuckDB registration paths.

## Findings
- No CQL logical operator spec violations found.
- Added regression coverage for measure-facing population SQL through query `let`/`where`/`return`.
- Corrected the parser class precedence comment to match the implementation and CQL Table 3-F.

## Focused Verification
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py -q`
- Result: 3 passed.
