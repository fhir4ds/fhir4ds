# Engineer Handoff - CQL-08 EXPLORER

All QA findings were reproduced and fixed surgically.

Resolved issues:

- `QA-001` Boolean `Coalesce` public helper: `fhir4ds/cql/duckdb/udf/logical.py` now wraps Boolean `Coalesce` return values as explicit DuckDB VARIANT values when using VARIANT return type. `fhir4ds/cql/duckdb/macros/logical.py` now lets `IsTrue`/`IsFalse` recognize VARIANT JSON `true`/`false` while preserving false results for string and numeric values.
- `QA-002` Quantity `Coalesce` comparison: `fhir4ds/cql/translator/expressions/_operators.py` now recognizes SQL `COALESCE` branches and CQL `Coalesce`/list/query expressions that produce Quantity values so comparisons route through `quantity_compare`.
- `QA-003` Boolean defaults and Quantity.value: `fhir4ds/cql/translator/expressions/_functions.py` no longer treats Boolean literals as numeric for `Coalesce`, and converts FHIRPath text/scalar Boolean paths to `fhirpath_bool` when a Boolean Coalesce peer proves the target type. `_operators.py` no longer propagates Quantity type through `.value` on a Quantity source, so Quantity.value remains Decimal.

Regression coverage was added to `fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py` and the fresh probe `.temp/qa/cql08_explorer_probe.py`.

Validation passed:

- Fresh EXPLORER probe passed.
- Nullological parity 11/11.
- Official nullological compliance 44/44.
- CMS832 DQM single-measure accuracy 100.0%.
- Adjacent CQL parity 77/77.
- Full conformance 2822/2822.
