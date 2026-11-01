# Engineer Handoff - CQL-10 HISTORIAN

Resolved issues:

- `QA-001`: Added omitted-precision support for `HighBoundary` and `LowBoundary`. Python fallback now computes default precision at runtime and exposes a default-argument macro over private UDFs. Native C++ now has one-argument VARCHAR and DOUBLE overloads using CQL default precision. The CQL extension was rebuilt and the bundled extension copied into `fhir4ds/cql/duckdb/extensions/`.
- `QA-002`: Corrected `Log` to the CQL two-argument value/base operator. The public SQL macro is now `Log(x, base)`, `LogBase` remains as an alias, and translated CQL rejects one-argument `Log(x)` with `TranslationError`; natural log remains `Ln(x)`.

Changed files:

- `fhir4ds/cql/duckdb/macros/math.py`
- `fhir4ds/cql/duckdb/udf/math.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py`
- `fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py`
- `extensions/cql/src/cql/boundary.hpp`
- `extensions/cql/src/cql/boundary.cpp`
- `extensions/cql/src/cql_extension.cpp`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
- `.temp/qa/cql10_historian_probe.py`

Validation:

- Fresh probe: `.temp/qa/cql10_historian_probe.py` passed.
- Focused parity: `test_arithmetic_operator_parity.py` 7/7 passed.
- No-Python/browser-style probes and focused tests passed for boundary defaults and `Log`.
- Official CQL arithmetic compliance: 348/348 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
