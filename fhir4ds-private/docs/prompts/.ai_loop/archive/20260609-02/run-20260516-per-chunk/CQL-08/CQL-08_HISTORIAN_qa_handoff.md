# CQL-08 HISTORIAN QA Handoff

## Scope
- Chunk: CQL-08 Nullological Operators.
- Items: `Coalesce`, `IsNull`, `IsFalse`, `IsTrue`.
- Personality focus: historical CQL XML examples, direct public DuckDB surfaces, translated scalar/query contexts, and native-loaded versus forced Python fallback parity.

## Findings
- `IsTrue(NULL::BOOLEAN)` and `IsFalse(NULL::BOOLEAN)` returned SQL NULL instead of false.
- `DateTime(year, month, day)` lost DateTime identity by emitting a date-shaped string instead of a day-precision DateTime marker.
- Direct public `Coalesce` over TIMESTAMP values failed in the Python fallback surface.
- Python and native C++ helper parsers did not accept the explicit `YYYY-MM-DDT` day-precision DateTime marker.
- Restoring the marker exposed official CQL regressions in DateTime predecessor/successor and DateTime interval contains/meets/collapse/except behavior.
- DQM focused runs exposed a regression in full timestamp open-bound interval normalization: midnight full timestamps were treated as day-precision bounds.

## Coverage Added
- Direct nullological parity coverage for `Coalesce`, `IsNull`, `IsTrue`, and `IsFalse`.
- Native-loaded and forced Python fallback parity for day-precision DateTime nullological examples.
- Native C++ browser/WASM surface tests for day marker predecessor/successor, date arithmetic marker preservation, interval overlap, collapse, and contains.
- DQM regression coverage for full timestamp open-bound overlap and day-precision marker preservation.

## Verification
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py -q` -> 17 passed.
- `./build/release/test/unittest "*cql*"` in `extensions/cql` -> 628 assertions passed.
- `python3 conformance/scripts/run_cql.py` -> 1706/1706 passed.
- `python3 -m fhir4ds.dqm.tests.conformance --measure CMS165,CMS56 --verbose` -> both measures 100%.
- `python3 -m pytest fhir4ds -q` -> 7157 passed, 5 skipped.
- `python3 conformance/scripts/run_all.py` -> 2822/2822 passed.

## Open Issues
None.
