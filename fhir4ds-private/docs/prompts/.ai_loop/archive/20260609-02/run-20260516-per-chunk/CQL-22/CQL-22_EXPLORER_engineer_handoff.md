# Engineer Handoff - CQL-22 EXPLORER

Resolved `QA-001`.

Root cause:
- `CQLMessage` used nullable SQL concatenation inside the DuckDB macro:
  `CAST(code AS VARCHAR) || ': ' || CAST(message AS VARCHAR)`.
- With `severity = 'Error'` and true condition, NULL `code` or NULL `message`
  made the argument to DuckDB `error(...)` NULL, so the expression returned SQL
  NULL instead of stopping evaluation.

Fix:
- Updated `fhir4ds/cql/duckdb/udf/math.py` so the macro coalesces nullable
  diagnostic text before calling `error(...)`.
- Mirrored the same NULL-safe formatting in the Python fallback body.
- Added parity coverage in
  `fhir4ds/cql/duckdb/tests/integration/test_message_parity.py` for direct
  `CQLMessage` and translated CQL `Message(...)` with NULL code/message across
  forced Python fallback and native-loaded DuckDB registrations.

Validation:
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_message_parity.py -q --tb=short`
  - 5 passed.
- Post-fix QA probe:
  - NULL message Error raises on forced Python fallback and native-loaded paths.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`
  - ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/ --tb=short`
  - 7233 passed, 5 skipped, 9 warnings.

No new issues discovered.
