# FP-18 HISTORIAN Engineer Handoff

Resolved QA-FP18-HIST-001.

Root cause: `fhir4ds/fhirpath/engine/nodes.py::FP_TimeBase._plus_time()` handled minute/second/millisecond precision but skipped hour-only `Time` precision. A finer quantity such as `61 minutes` was therefore ignored for `@T12`. The same missing branch let invalid date-valued units on hour-only `Time`, such as `@T12 + 1 day`, fall through as unchanged `T12`.

Fix: Added explicit Time unit validation for `hour`, `minute`, `second`, and `millisecond`, plus a `precision == 1` branch that converts finer units down to whole hours using truncation toward zero before adding. Added native/fallback public UDF parity regressions in `test_arithmetic_parity.py` for `@T12 + 61 minutes -> T13` and `@T12 + 1 day -> empty/invalid`.

Validation completed before architect phase:
- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/fp18_historian_probe.py` passed 34 expressions.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py -q` passed 22 tests.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_new_functions.py fhir4ds/fhirpath/tests/unit/test_new_functions.py -q` passed 118 tests.
- Native CLI smoke with the built extension returned `["T13"]` for `@T12 + 61 minutes` and `false` for `fhirpath_is_valid('@T12 + 1 day')`.

No C++ files were changed for this FP-18 HISTORIAN fix; no native rebuild/copy was required.
