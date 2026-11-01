# QA Handoff - CQL-20 HISTORIAN

Scope: CQL Aggregate Functions (`AllTrue`, `AnyTrue`, `Avg`, `Count`,
`GeometricMean`, `Max`, `Min`, `Median`, `Mode`, population/sample variance and
stddev, `Product`, `Sum`).

Spec anchors:
- CQL 1.5.3 Reference Appendix B Aggregate Functions:
  https://cql.hl7.org/09-b-cqlreference.html#aggregate-functions
- CQL 1.5.3 Logical Specification Aggregate Operators:
  https://cql.hl7.org/04-logicalspecification.html#aggregate-operators

Fresh probes:
- `.temp/qa/cql20_historian_probe.py` checked direct public aggregate helpers,
  translated list/query aggregate sources, Quantity unit-aware aggregates,
  null/empty/all-null behavior, invalid string coercion, and Python fallback vs
  native-loaded vs no-Python extension parity.

Finding:
- `CQL20-HISTORIAN-001` HIGH SPEC_VIOLATION: static aggregate validation did
  not classify nested list, tuple, interval, typed instance, constructor, `as`
  assertion, or known conversion/function-return elements inside simple list
  literals. Invalid aggregate calls such as `AllTrue({{1, 2}})`,
  `Avg({ToString(5)})`, `Avg({DateTime(2012, 1, 1)})`, and
  `Min({Tuple { a: 1 }, Tuple { a: 2 }})` translated instead of raising at the
  CQL boundary.

Validation after remediation:
- `PYTHONPATH=. python3 .temp/qa/cql20_historian_probe.py` -> PASS.
- `PYTHONPATH=. python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py -q` -> 9 passed.
- Official `CqlAggregateFunctionsTest.xml` -> 50/50 passed.
- Full conformance -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
