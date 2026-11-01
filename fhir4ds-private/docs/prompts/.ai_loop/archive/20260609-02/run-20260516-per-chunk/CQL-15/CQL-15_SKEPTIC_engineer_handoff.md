# Engineer Handoff - CQL-15 SKEPTIC

Issue fixed: `QA-001` HIGH, CQL interval `start`/`end` returned excluded open boundaries instead of semantic effective boundaries.

Root cause:
- Python fallback `intervalStart`/`intervalEnd` parsed and normalized open discrete boundaries, but then returned the raw authored low/high values before using the normalized effective bounds.
- Native C++ `Interval::start_string()` and `Interval::end_string()` returned raw low/high values rather than `effective_start_bound`/`effective_end_bound`.
- Translator fallback extraction for identifier/CTE interval expressions treated `intervalStart(...)`/`intervalEnd(...)` helper results as if the original interval could still be half-open, which double-excluded CMS half-open measurement period logic once the helpers were corrected.

Resolution:
- `fhir4ds/cql/duckdb/udf/interval.py` now returns raw bounds only for authored closed boundaries; open bounds return successor/predecessor effective values with Date/DateTime formatting preserved.
- `extensions/cql/src/cql/interval.cpp` now routes `Interval::start_string()`/`end_string()` through effective boundary helpers, including day-precision DateTime marker preservation.
- `extensions/cql/src/cql_extension.cpp` uses the corrected interval string methods for native/no-Python public helper registration.
- `fhir4ds/cql/translator/expressions/_temporal_intervals.py` treats `intervalStart(...)`/`intervalEnd(...)` fallback helper outputs as closed semantic bounds.
- Rebuilt and copied `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` from the native C++ build.

Regression coverage added:
- Forced Python fallback and native-loaded interval Part 1 parity for integer, Date, and day-precision DateTime open start/end.
- Translated scalar CQL `start of`/`end of` open-bound cases.
- CMS159-shaped `ends during day of Interval[..., ...)` regression to protect half-open measurement-period comparisons.
- No-Python/browser-style C++ direct helper checks for `intervalStart`/`intervalEnd` open boundaries.
- Existing interval UDF unit expectations updated to CQL effective-bound semantics.

Verification:
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py -q` -> 6 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py fhir4ds/cql/duckdb/tests/test_interval_udfs.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q` -> 73 passed.
- `./build/release/test/unittest "*cql*"` from `extensions/cql` -> all tests passed, 694 assertions.
- `python3 -m fhir4ds.dqm.tests.conformance.cli --measure CMS159 --suite 2025 --skip-errors --verbose` -> CMS159 67/67, 100.0%.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `git diff --check` -> clean.
