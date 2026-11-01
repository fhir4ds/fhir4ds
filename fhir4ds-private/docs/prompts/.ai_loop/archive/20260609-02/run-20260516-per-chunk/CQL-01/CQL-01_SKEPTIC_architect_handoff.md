# Architect Handoff — CQL-01 SKEPTIC

Architect audit result: CLEAN.

Golden standard used:
- CQL primitive behavior is defined by System type semantics, not DuckDB storage coincidences.
- `System.Any` is the maximal supertype and must not route through FHIR resource-type checks for primitive values.
- Integer/Long/Decimal literal boundaries must be spec-bounded and preserve authored precision where needed.
- Public DuckDB native-loaded and forced Python fallback registrations must agree for primitive conversion functions.

Review outcome:
- The three CQL-01 issues are resolved with general fixes, not case-specific patches.
- `SQLLiteral.raw_sql` is currently fed by parser Decimal tokens only; the lexer restricts that token text to digits plus one decimal point, so the exact-rendering change does not introduce a SQL injection path.
- The translation simplifications for literal unary minus and literal type checks are semantically valid. Two existing integration tests asserted old internal AST shapes, so they were updated to assert the resulting semantics.
- No new CRITICAL/HIGH/MEDIUM findings remain. `RETRY_QA` is not set.

Validation:
- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/cql01_probe.py` — passed; fixed translator and native/fallback DuckDB probe outputs matched expectations.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py -q --tb=short` — 4 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py -q --tb=short` — 7 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py -k 'CqlTypesTest or ValueLiteralsAndSelectors or CqlTypeOperatorsTest' -q --tb=short` — 195 passed, 2849 deselected.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py -q --tb=short` — 3044 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/tests/unit fhir4ds/cql/tests/integration fhir4ds/cql/duckdb/tests/integration -q --tb=short` — 1358 passed, 5 skipped.
- `cd extensions/cql && ./build/release/test/unittest "*cql*"` — 612 assertions passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` — 2822/2822 passed.
- `git diff --check` — passed.
