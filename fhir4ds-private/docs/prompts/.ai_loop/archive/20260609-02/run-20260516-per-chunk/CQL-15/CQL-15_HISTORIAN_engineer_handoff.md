# Engineer Handoff - CQL-15 HISTORIAN

Remediation completed:
- Added `intervalEquals` and `intervalEquivalent` helper surfaces in Python
  fallback and native C++.
- Routed translated interval `=`, `!=`, `~`, and `!~` through semantic interval
  helpers instead of raw SQL/JSON comparison.
- Updated precision-aware Python interval helpers to return NULL for partial
  Date/DateTime uncertainty.
- Updated native C++ precision-aware interval helpers to return SQL NULL for
  uncertain partial Date/DateTime comparisons.
- Updated native C++ `intervalStartsSame`/`intervalEndsSame` to return NULL when
  the required low/high boundary is missing.
- Rebuilt and copied the bundled CQL DuckDB extension.
- Added focused parity tests for direct helper behavior and translated interval
  equality/equivalence.

Important files changed:
- `fhir4ds/cql/duckdb/udf/interval.py`
- `fhir4ds/cql/duckdb/extension.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `extensions/cql/src/cql/interval.cpp`
- `extensions/cql/src/cql_extension.cpp`
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py`

Verification:
- `./build/release/test/unittest "*cql*"`: passed, 694 assertions.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py -q`: 8 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py fhir4ds/cql/duckdb/tests/test_interval_udfs.py -q`: 70 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py`: 2822/2822 overall.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql -q --tb=short`: 4959 passed, 5 skipped, 6 warnings.
- Native and bundled CQL extension SHA-256:
  `ff61d3c45671541b38a6bbaec59a711c05c6cefd5ccdeaed533c29fe069ec233`.

Residual notes:
- Direct `expand('<single interval>', per)` remains a binder-level mismatch
  because the public overload accepts interval arrays. Translated CQL uses the
  appropriate expansion path and was not part of the remediated defects.
