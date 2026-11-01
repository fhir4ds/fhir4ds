# Engineer Handoff - CQL-12 SKEPTIC

Chunk: CQL-12, CQL String Operators.

Resolved implementation changes:
- `fhir4ds/cql/duckdb/macros/list.py`: `Combine` and `CombineSep` now return `NULL` when the non-null filtered list is empty.
- `fhir4ds/cql/duckdb/macros/string.py`: `Substring` and `SubstringLen` now return `NULL` for null/negative/at-or-past-end starts and negative lengths.
- `fhir4ds/cql/duckdb/udf/string.py`: deprecated Python string UDFs now preserve row-level resilience for null search operands and substring boundary failures.
- `fhir4ds/cql/translator/expressions/_functions.py`: translated `Substring` includes CQL null-result boundary guards; translated `StartsWith` and `EndsWith` call exact-match macros instead of lowering to `LIKE`.
- `fhir4ds/cql/translator/expressions/_lists.py`: string indexer sources are detected and routed through the public `Indexer` macro instead of list extraction.
- `fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py`: added native-loaded vs forced Python fallback parity checks and no-Python/browser-style direct macro regression probes.

Backend coverage:
- Native-loaded DuckDB registration and forced Python fallback were both executed for translated string operator regressions.
- No-Python/browser-style direct macro coverage was executed for the public SQL surface.
- Native C++ CQL unittest was run even though this pass did not require C++ source changes.

No unresolved engineering items remain from this personality.
