# QA Handoff: CQL-20 EXPLORER

Scope: fresh EXPLORER pass for CQL Aggregate Functions. I probed aggregate
calls over query-produced lists, nested expression arguments, direct public
helpers, invalid element types, null/empty behavior, variance/stddev edge
cases, mode ties, Product/GeometricMean zero and negative boundaries, and
forced Python fallback vs native-loaded vs no-Python C++ parity.

Spec anchors: CQL Reference Aggregate Functions and CQL Logical Specification
Aggregate Operators. Aggregate functions operate over typed list inputs;
Boolean aggregates are Boolean-list functions, numeric/statistical aggregates
are numeric-list functions, `Product` is the multiplicative aggregate, and
invalid element types must not be accepted through implementation casts or SQL
truthiness.

Fresh probe: `.temp/qa/cql20_explorer_probe.py`.

Issues found:

1. `CQL20-EXPLORER-001` HIGH: translated query-form `Product(...)` over a
   scalar query source emitted bare `PRODUCT(_val)`. The direct CQL `Product`
   list macro shadows DuckDB's row aggregate, so spec-supported
   `Product((from { 2.0, 0.0, null as Decimal, 4.0 } D return D))` failed at
   bind time instead of returning `0.0`.
2. `CQL20-EXPLORER-002` HIGH: static aggregate validation did not infer simple
   query-produced list element types, so invalid static queries such as
   `AllTrue((from { 1, 2 } I return I))`,
   `Avg((from { '1', '2' } S return S))`,
   `Sum((from { @2012-01-01T00:00:00 } D return D))`, and
   `Min((from { Tuple { a: 1 } } T return T))` translated to SQL instead of
   raising `TranslationError`.

Validation evidence before handoff:

- Fresh EXPLORER probe initially reproduced both issues, then passed after
  remediation.
- Aggregate parity pytest: `9 passed`.
- Adjacent aggregate macro/WASM checks: `14 passed`.
- Official aggregate runner output included `CqlAggregateFunctionsTest.xml:
  50/50 passed` and `CqlAggregateTest.xml: 9/9 passed`.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
