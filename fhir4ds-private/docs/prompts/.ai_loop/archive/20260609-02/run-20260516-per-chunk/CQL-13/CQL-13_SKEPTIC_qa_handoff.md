# CQL-13 SKEPTIC QA Handoff

## Scope

CQL Date/Time Operators Part 1:

- Add left DateTime/right Quantity
- After/Before precision of
- Date and DateTime constructors
- Component From precision
- Difference in precision between
- Duration in precision between

## Findings

The SKEPTIC pass found 8 resolved issues:

1. Dynamic DateTime constructor hour precision formatting was incomplete.
2. Runtime timezone offsets lost half-hour precision.
3. `time from DateTime(...)` did not preserve the right null/precision behavior.
4. `DifferenceBetween` needed the same uncertainty-aware public helper surface as `DurationBetween`.
5. Partial DateTime marker values such as `2003T` and `2003-10T` were not preserved.
6. Native C++ `dateAddQuantity` widened hour/minute/marker precision.
7. Direct `dateComponent` did not respect missing components or time-only values.
8. Duration/difference scalar-or-interval `VARCHAR` results regressed arithmetic, `div`, list aggregation, and DQM measure SQL until numeric boundaries were made explicit.

## Coverage Added

- Forced Python fallback vs native-loaded DuckDB parity for DateTime constructors, timezone offsets, `time from`, `DurationBetween`, `DifferenceBetween`, uncertainty comparisons, `/`, and `div`.
- No-Python/browser-style C++ surface coverage for `dateAddQuantity`, `dateComponent`, and `cqlDurationBetween`.
- Native C++ SQL tests for `dateComponent`, `cqlDurationBetween`, `cqlDifferenceBetween`, timezone millisecond difference, and DateTime marker arithmetic.
- DQM regression target for CMS0334 plus full DQM conformance.

## Verification

- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py fhir4ds/cql/tests/unit/test_v2_expressions.py::TestDifferenceBetween -q` -> 10 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m fhir4ds.dqm.tests.conformance --measure CMS0334 --output .temp/qa/cql13_skeptic_cms0334_after_div --skip-errors` -> 135/135, 100%.
- `python3 conformance/scripts/run_dqm.py` -> 47/47.
- `python3 conformance/scripts/run_cql.py` -> 1706/1706.
- `python3 conformance/scripts/run_all.py` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `python3 -m pytest fhir4ds -q` -> 7180 passed, 5 skipped, 9 warnings.
- `cd extensions/cql && ./build/release/test/unittest "*cql*"` -> 694 assertions passed.
- `git diff --check` -> clean.
