# Engineer Handoff: CQL-04 SKEPTIC

Resolved both QA findings.

Fixes:
- Hardened `fhir4ds/cql/duckdb/macros/logical.py` with guarded Boolean helper
  macros so public direct `And`, `Or`, `Xor`, `Implies`, and `Not` return SQL
  NULL for invalid direct operands instead of using DuckDB truthiness.
- Added a guarded `logicalImplies` macro for Python fallback/native-loaded
  registrations and made logical UDF registration skip pre-existing macro/native
  names without aborting the rest of the logical UDF group.
- Hardened `extensions/cql/src/cql_extension.cpp` so the no-Python/browser-style
  VARCHAR `logicalImplies` overload accepts only `true`/`false` Boolean text
  and returns NULL for malformed strings.
- Extended static logical operand inference in
  `fhir4ds/cql/translator/expressions/_operators.py` for `CodeSelector`,
  clinical instances, Quantity/temporal literals, Intervals, Tuples, Lists, and
  typed parameters.
- Added regression coverage in `test_logical_parity.py`,
  `test_wasm_cpp_surface.py`, and `extensions/cql/test/sql/cql.test`.
- Rebuilt `extensions/cql/build/release/extension/cql/cql.duckdb_extension` and
  copied it to `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.

Validation:
- `python3 .temp/qa/cql04_skeptic_probe.py`: passed
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py::test_cql_browser_logical_and_list_udfs_run_without_python_fallback -q`: 15 passed
- `./extensions/cql/build/release/test/unittest "*cql*" | tail -n 40`: 784 assertions passed
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822
