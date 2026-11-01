# Engineer Handoff - CQL-03 EXPLORER

Phase: FIX
Status: Complete

## Issues Resolved

### CQL03-EXPLORER-001

Root cause: Translated CQL `ToDate`/`ToDateTime` and `convert ... to Date/DateTime` used local SQLRaw/TRY_CAST logic rather than the spec-aware DuckDB conversion macros. That path rejected valid partial precision values such as `2014` and `2014-01`, and preserved invalid calendar strings such as `2024-02-30`.

Fix: `fhir4ds/cql/translator/expressions/_functions.py` and `_operators.py` now lower temporal conversion functions and convert expressions to `ToDate(...)` / `ToDateTime(...)` macro calls.

### CQL03-EXPLORER-002

Root cause: Python fallback Ratio UDFs returned raw JSON values and divided them without Decimal-shape validation. Malformed internals raised Python/DuckDB errors while the native-loaded path returned NULL.

Fix: `fhir4ds/cql/duckdb/udf/ratio.py` validates finite Decimal numeric fields before returning numerator/denominator values or calculating `ratioValue`.

## Tests Added/Updated

- `fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py`
  - translated temporal conversion regression cases for valid partial precision and invalid calendar values.
  - malformed Ratio numeric internals must return NULL under both native-loaded and forced Python fallback registration.
- `fhir4ds/cql/tests/unit/test_v2_expressions.py`
  - updated conversion-function lowering expectations to spec-aware macro calls.
- `extensions/cql/AGENTS.md`
  - marked CQL-03 temporal/complex boundary finding fixed and documented guardrails.

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py fhir4ds/cql/tests/unit/test_v2_expressions.py -q`
  - 151 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py -q`
  - 5 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql -q`
  - 4899 passed, 5 skipped
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py -q`
  - 3044 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py`
  - ViewDefinition: 134/134
  - FHIRPath R4: 935/935
  - CQL: 1706/1706
  - DQM: 47/47
  - Overall: 2822/2822

No C++ native code changed; no extension rebuild/copy was required.
