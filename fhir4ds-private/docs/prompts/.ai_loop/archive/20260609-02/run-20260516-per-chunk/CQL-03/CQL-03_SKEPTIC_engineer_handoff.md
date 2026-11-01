# Engineer Handoff - CQL-03 SKEPTIC

Resolved issues:
- `CQL03-SK-001`: Added CQL-aware temporal validators in `fhir4ds/cql/duckdb/udf/conversion.py` and routed `ToDate`, `ToDateTime`, and `ToTime` macros through private helper UDFs in `fhir4ds/cql/duckdb/macros/conversion.py`. This preserves partial precision strings such as `2014-01`, preserves explicit DateTime offsets, normalizes DateTime `Z` to `+00:00`, accepts official ToTime timezone suffixes, and rejects invalid dates/times/timezone offsets.
- `CQL03-SK-002`: Tightened `toQuantity()` numeric parsing in `fhir4ds/cql/duckdb/udf/quantity.py` so malformed decimals return `NULL` and `ConvertsToQuantity` returns `false` instead of raising.
- `CQL03-SK-003`: Implemented spec string-form ratio parsing in `ToRatio`/`ConvertsToRatio` while retaining internal JSON-shaped ratio support only when numerator and denominator are valid Quantity objects with numeric values.

Regression tests added/updated:
- `fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py`

Focused validation already passing:
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py -q` -> 8 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/test_quantity_udf.py fhir4ds/cql/duckdb/tests/test_ratio_udfs.py fhir4ds/cql/duckdb/tests/test_macros_tier1.py -q` -> 149 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests -q` -> 516 passed, 5 skipped
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_cql.py | grep -E "FAIL|ERROR|Summary|CqlTypeOperators|passed"` -> 1706/1706
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` -> overall 2822/2822

No C++ CQL source was changed; native parity issues were in Python supplement/macros that are active on both native-loaded and forced fallback connections.
