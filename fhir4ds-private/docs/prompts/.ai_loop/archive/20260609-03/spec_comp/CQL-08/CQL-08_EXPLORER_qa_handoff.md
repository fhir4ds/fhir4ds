# QA Handoff - CQL-08 EXPLORER

Scope: CQL nullological operators `Coalesce`, `IsNull`, `IsFalse`, and `IsTrue` under EXPLORER composition testing.

Spec reference: CQL 1.5.3 Appendix B nullological operators. `Coalesce<T>` returns the first non-null value from either 2-5 scalar arguments or one `List<T>` argument; `IsTrue` and `IsFalse` are exact Boolean predicates and must not inherit SQL numeric/string truthiness; `IsNull` checks only null, not empty lists or lists containing nulls.

Fresh probe: `.temp/qa/cql08_explorer_probe.py`.

Findings:

- `QA-001` HIGH: public direct DuckDB `Coalesce` failed to preserve Boolean `T` for scalar and list overloads, and `IsTrue`/`IsFalse` over Boolean Coalesce results did not recognize VARIANT-transported Boolean values.
- `QA-002` HIGH: translated Quantity-producing `Coalesce`, including query-list `Coalesce`, lost Quantity semantics before comparison and could return NULL or scalar conversion errors instead of using `quantity_compare`.
- `QA-003` HIGH: translated `Coalesce(Patient.active, false)` treated Boolean literals as numeric and failed/erased FHIR Boolean values; the Quantity inference fix also exposed that `.value` on a Quantity-producing Coalesce source must be Decimal, not Quantity.

Validation after remediation:

- `.temp/qa/cql08_explorer_probe.py`: passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py -q`: 11 passed.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py -k nullological -q`: 44 passed, 3000 deselected.
- `python3 -m fhir4ds.dqm.tests.conformance.cli --measure CMS832 --output .temp/qa/cql08_cms832_probe --suite 2025 --skip-errors --verbose`: CMS832 accuracy 100.0% (34/34).
- Adjacent parity: primitive/logical/clinical-type/structural 62 passed; arithmetic/clinical-operator 15 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
