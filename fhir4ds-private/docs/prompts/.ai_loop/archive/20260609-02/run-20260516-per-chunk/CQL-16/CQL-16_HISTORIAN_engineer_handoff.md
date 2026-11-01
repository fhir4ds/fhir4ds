# Engineer Handoff - CQL-16 HISTORIAN

Resolved `QA-001` and `QA-002`.

Changes made:

- Added null-aware no-Python C++ `intervalEquivalent` handling in
  `extensions/cql/src/cql_extension.cpp`: both SQL NULL operands return true;
  exactly one SQL NULL operand returns false; parsed interval operands continue
  through semantic interval equivalence.
- Added interval-bound temporal string parsing in `extensions/cql/src/cql/interval.cpp`
  and declaration in `extensions/cql/src/cql/interval.hpp`. Year-only strings
  such as `2014`, Date/DateTime-looking strings, and time strings are parsed as
  temporal values only in interval-bound contexts before falling back to generic
  string parsing.
- Updated precision point handling in `intervalContainsPrecise` so DateTime
  point strings are parsed as temporal values for precision-aware contains.
- Updated CQL translator `included in <precision> of` to route interval operands
  to `intervalIncludedInPrecise` and point operands to `intervalContainsPrecise`.
- Kept translated `overlaps <precision> of` on the existing DQM day-window
  decomposition for dynamic/resource intervals, while folding static partial
  temporal interval literals to SQL NULL when requested precision exceeds the
  authored precision.
- Added parity/regression coverage in
  `fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py` and
  native SQL assertions in `extensions/cql/test/sql/cql.test`.
- Rebuilt `extensions/cql/build/release/extension/cql/cql.duckdb_extension`
  and copied it to `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.

Validation:

- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py -q --tb=short`:
  4 passed.
- Interval/browser cluster:
  81 passed.
- `./build/release/test/unittest "*cql*"`:
  718 assertions passed in 2 test cases.
- `python3 conformance/scripts/run_all.py`:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall
  2822/2822.
- `python3 -m pytest -q --tb=short`:
  7200 passed, 5 skipped, 9 warnings.

No new open issues discovered.
