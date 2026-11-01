# QA Handoff: CQL-20 SKEPTIC

Scope: CQL Aggregate Functions (`AllTrue`, `AnyTrue`, `Avg`, `Count`,
`GeometricMean`, `Max`, `Min`, `Median`, `Mode`, `PopulationStdDev`,
`PopulationVariance`, `Product`, `StdDev`, `Sum`, `Variance`).

Spec basis: CQL Reference Appendix B aggregate functions. Aggregate operators
consume list values; `AllTrue`/`AnyTrue` are Boolean-list operators, numeric and
statistical aggregates require supported numeric/Quantity element types, and
`GeometricMean(X)` is defined through `Power(Product(X), 1 / Count(X))`.

Fresh probes found two HIGH issues:

- `QA-001`: translated aggregate functions and several direct list macros
  silently coerced invalid string/non-Boolean list elements through DuckDB casts.
  Examples included `Avg({'1','2'})`, `Product({'2','3'})`,
  `Median({'1','2'})`, `AllTrue({1,2})`, and direct
  `SELECT Median(['1','2'])`.
- `QA-002`: `GeometricMean({0.0,4.0})` raised a logarithm-of-zero error instead
  of returning `0`, and query-produced GeometricMean sources were passed as
  row-producing subqueries rather than scalar lists.

Fresh reproducer/verification probe: `.temp/qa/cql20_skeptic_probe.py`.
