# QA Handoff — CQL-20 EXPLORER

## Scope

Fresh EXPLORER pass over CQL Aggregate Functions using current source, HL7 CQL
1.5.3 Appendix B aggregate semantics, current tests, and new probes only. No
archived workflow outputs were used as proof.

## Hypotheses Probed

1. Direct aggregate helper names might still behave like DuckDB row aggregates
   instead of CQL list functions.
2. Query-shaped list sources might diverge from inline list literals.
3. Null-heavy aggregate inputs might leak DuckDB defaults instead of CQL
   defaults.
4. Non-numeric `Max`/`Min` signatures might be accidentally handled as numeric
   aggregates.

## Fresh Probe

Created `.temp/qa/cql20_explorer_probe.py`.

Result before remediation:

- `QueryDateMax`, `QueryDateMin`, `QueryStringMax`, and `QueryTimeMin` all
  returned SQL NULL across forced Python fallback, native-loaded registration,
  and no-Python/browser-style C++.
- Direct `Median(list)` and `Mode(list)` returned the input list, while direct
  `StdDev(list)`, `Variance(list)`, `PopulationStdDev(list)`, and
  `PopulationVariance(list)` raised DuckDB binder errors.

## Open Issues

- `QA-001` MEDIUM: query-shaped `Max`/`Min` over Date, Time, and String sources
  are cast to `DOUBLE` and return NULL.
- `QA-002` MEDIUM: direct statistical aggregate macros route list inputs to
  DuckDB row aggregate functions instead of CQL list semantics.
