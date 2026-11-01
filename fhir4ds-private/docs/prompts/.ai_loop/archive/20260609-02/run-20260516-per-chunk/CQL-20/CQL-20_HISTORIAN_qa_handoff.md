# QA Handoff - CQL-20 HISTORIAN Aggregate Functions

Personality: HISTORIAN

Scope covered:
- CQL aggregate functions `AllTrue`, `AnyTrue`, `Avg`, `Count`,
  `GeometricMean`, `Max`, `Min`, `Median`, `Mode`, `PopulationStdDev`,
  `PopulationVariance`, `Product`, `StdDev`, `Sum`, and `Variance`.
- Fresh translated CQL probes, direct helper probes, and parity checks across
  forced Python fallback, native-loaded registration, and no-Python/browser-style
  C++ plus SQL macro execution where applicable.
- Spec basis: HL7 CQL Reference Appendix B aggregate functions, including
  list-source aggregate signatures and null/empty semantics.

Findings:
- `QA-001` MEDIUM: query-shaped list sources for aggregate functions were
  incorrectly treated as CTE-backed tables and received patient_id correlation.
  Fresh reproducer: `AllTrue((from { true, null as Boolean, true } B return B))`
  emitted `_list.patient_id = _pt.patient_id`, causing DuckDB binder failure.
  The same row aggregate path also needed CQL boolean defaults for null-only
  query sources.
- `QA-002` MEDIUM: translated list `Mode` used DuckDB `list_aggregate(...,
  'mode')`, which chooses a value for tied modes. The public
  `statisticalMode` helper surface returns SQL NULL for tied most-frequent
  values, so translated CQL and public helper semantics diverged.

Fresh probe:
- `.temp/qa/cql20_historian_probe.py`
