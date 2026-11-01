# CQL-13 HISTORIAN QA Handoff

## Scope

Independent HISTORIAN audit of CQL Date/Time Operators Part 1 after SKEPTIC fixes.

## Findings

Two distinct residual issues were found and resolved:

1. `date from DateTime(2012)` and `date from DateTime(2012, 5)` returned DateTime marker strings (`2012T`, `2012-05T`) instead of Date values.
2. Python fallback accepted invalid timezone offsets such as `+14:30` while the no-Python C++ helper surface returned NULL. The same pass found static decimal constructor components such as `DateTime(2012.5)` being truncated instead of rejected.

## Coverage Added

- Translated `date from DateTime(...)` parity for year, month, day, and hour precision DateTime inputs.
- Invalid timezone direct helper parity for `dateAddQuantity`, `dateSubtractQuantity`, `dateComponent`, `cqlBeforeP`, `cqlDurationBetween`, and `cqlDifferenceBetween`.
- No-Python C++ assertions for invalid timezone helper behavior.
- Constructor invalid tests for decimal Date/DateTime components.

## Verification

- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py::test_cql_browser_interval_and_boundary_udfs_run_without_python_fallback -q` -> 8 passed.
- `python3 conformance/scripts/run_cql.py` -> 1706/1706.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m fhir4ds.dqm.tests.conformance --measure CMS146 --output .temp/qa/cql13_historian_cms146_after_tz_guard2 --skip-errors` -> 10/10, 100%.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m fhir4ds.dqm.tests.conformance --measure CMS56 --output .temp/qa/cql13_historian_cms56_after_runall_failure --skip-errors` -> 58/58, 100%.
- `python3 conformance/scripts/run_dqm.py` -> 47/47.
- `python3 conformance/scripts/run_all.py` -> repeat run passed ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `python3 -m pytest fhir4ds -q` -> 7184 passed, 5 skipped, 9 warnings.
- `git diff --check` -> clean.
