# Architect Handoff: CQL-06 HISTORIAN

Structural health: acceptable after remediation. The fix is correctly located
at the public conversion boundary instead of generic Quantity arithmetic. The
brief DQM regression during validation showed why `parse_quantity` must remain a
runtime Quantity parser, while `ToQuantity`, `ConvertsToQuantity`,
`ConvertsToRatio`, and `ConvertQuantity` own conversion-check strictness.

Issue summary: 1 HIGH spec violation found, 1 resolved, 0 open.

Architect audit:

- No new architecture findings were logged.
- The code keeps conversion validation in `fhir4ds.cql.duckdb.udf.conversion`
  and Quantity formatting/parsing support in `fhir4ds.cql.duckdb.udf.quantity`.
- The native C++ change mirrors only the public `ToQuantity(VARCHAR)` string
  boundary and does not make C++ `parse_quantity_json` reject arithmetic
  intermediates.
- Native-loaded and forced Python fallback behavior are covered by the fresh
  probe and focused parity tests.

Recommended fix order: none. Continue to CQL-06 EXPLORER.
