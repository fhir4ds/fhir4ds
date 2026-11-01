# Engineer Handoff - FP-09 SKEPTIC

Resolved issues:
- `QA-001` HIGH: native C++ string search functions now enforce singleton/type constraints for String inputs/arguments and Integer `substring` arguments. Invalid cases such as `s.indexOf(123)`, `s.endsWith(123)`, `s.contains(123)`, `s.substring('1')`, and `num.contains('2')` now return empty/NULL through public DuckDB UDFs, matching forced Python fallback behavior.
- `QA-002` MEDIUM: Python core `substring()` now returns empty when `start >= len(string)`, so forced Python DuckDB fallback matches native C++ for `s.substring(6)` over `"abcdef"`.

Files changed:
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/engine/invocations/strings.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `extensions/fhirpath/AGENTS.md`

Validation run:
- `cmake --build build/release --config Release -j 8` from `extensions/fhirpath`
- `cp extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath` - 164 assertions passed
- Manual native and forced Python fallback SQL reproducers - all fixed
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py -q` - 2 passed
- `python3 -m pytest fhir4ds/fhirpath/tests -q --tb=short` - 169 passed
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests -q --tb=short` - 1006 passed, 1 existing warning
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` - ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822

No new issues discovered.
