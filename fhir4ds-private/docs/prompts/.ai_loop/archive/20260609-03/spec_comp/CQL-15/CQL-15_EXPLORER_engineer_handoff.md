# Engineer Handoff - CQL-15 EXPLORER

## Issues Resolved

- `QA-001`: Empty interval-list collapse returned SQL NULL on forced Python and native-loaded surfaces. Fixed Python `collapse_intervals` to return `[]` for a parsed empty list while preserving NULL for null/non-list inputs.
- `QA-002`: Incompatible `per` Quantity handling was too permissive. Fixed Python and C++ expand unit compatibility for numeric and temporal intervals, and translated statically incompatible `collapse ... per` to SQL NULL instead of silently dropping `per`.
- `ARCH-001`: Valid translated `collapse ... per` still ignored `per`. Fixed `_translate_collapse` so compatible `per` routes through `expand(list, per)` before `collapse_intervals(...)`, preserving the CQL partitioning semantics.

## Changed Code

- `fhir4ds/cql/duckdb/udf/interval.py`
- `extensions/cql/src/cql_extension.cpp`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
- `extensions/cql/build/release/repository/v1.5.2/linux_amd64/cql.duckdb_extension`
- `.temp/qa/cql15_explorer_probe.py`
- `extensions/cql/AGENTS.md`

## Validation

- `python3 .temp/qa/cql15_explorer_probe.py` -> PASS
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q` -> 27 passed
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_interval_operators -q` -> 412 passed
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> 2822/2822, 100.0%

## Notes

The C++ build emitted the pre-existing `DateTimeNowFunc` snprintf truncation warning. Full conformance still passed. The final valid-`per` output comparison is JSON-structural because Python and C++ differ only in whitespace when serializing JSON arrays.
