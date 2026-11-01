# QA Handoff — CQL-16 EXPLORER

## Scope
CQL-16 Interval Operators Part 2, EXPLORER personality. Fresh probes targeted compositional interval paths: nested `intersect`, open/closed boundaries, partial temporal precision, incompatible Quantity dimensions, translated CQL, public DuckDB helpers, native-loaded registration, forced Python fallback, and no-Python/native extension execution.

## Spec Basis
CQL Reference 1.5.3 Appendix B states that `overlaps` is true when interval endpoints overlap, uses Start/End boundary semantics, precision-qualified Date/DateTime/Time comparisons are evaluated at the requested precision, imprecise temporal comparisons may return null, and null arguments return null. `intersect` returns the overlapping interval or null when there is no overlap.

## Finding
- QA-001 HIGH: translated dynamic FHIR `Observation.effective` point values with partial precision bypass the precision-aware interval helper. Reproducer: an Observation with `effectiveDateTime: "2014"` evaluated as `O.effective overlaps day of Interval[@2014-06-01, @2014-06-02]` returns `false`; the static equivalent `Interval[@2014, @2014] overlaps day ...` returns `null`. The same uncertainty rule should apply to the dynamic point value.

## Validation Already Run
- `PYTHONPATH=. python3 .temp/qa/cql16_explorer_probe.py`: passed before adding the dynamic partial reproducer.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py -q`: 5 passed.

## Next Step
Remediate the precision-qualified translated `overlaps`, `overlaps before`, and `overlaps after` paths so runtime FHIR point values are converted to degenerate intervals before calling precision-aware interval helpers, while preserving Period/interval JSON values as intervals.
