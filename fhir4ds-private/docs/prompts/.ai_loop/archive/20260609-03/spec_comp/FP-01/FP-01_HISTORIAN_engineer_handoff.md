# Engineer Handoff - FP-01 HISTORIAN

Status: FIX_COMPLETE

Issues remediated:
- QA-001: Typed DuckDB wrappers now return values only for their declared literal class. Python fallback uses raw evaluator results for `fhirpath_timestamp` and `fhirpath_quantity`; native C++ uses FPValue type/shape guards before stringifying.
- QA-002: Python fallback now rejects invalid timezone placement in Date and partial-DateTime literals before compile and in `fhirpath_is_valid`.
- QA-003: Python fallback and native C++ now enforce the FHIRPath 32-bit Integer literal range while preserving valid `(-2147483648)`.

Additional parity hardening:
- Python fallback normalizes no-whitespace quoted UCUM Quantity literals such as `10'mg'` before parser compilation.
- Literal parity tests create the forced Python fallback connection before loading the native extension to avoid connection-level function contamination.
- The QA probe now inserts the workspace root on `sys.path` and runs native/fallback checks in separate subprocesses.

Validation:
- `python3 -m py_compile fhir4ds/fhirpath/duckdb/evaluator.py fhir4ds/fhirpath/duckdb/udf.py .temp/qa/fp01_historian_literal_probe.py`
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q` -> 24 passed
- `cmake --build build/release --config Release -j 8`
- `./build/release/test/unittest '*fhirpath*'` -> 326 assertions passed
- `python3 .temp/qa/fp01_historian_literal_probe.py`
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> 2822/2822, 100.0%

No open engineer work remains for this inner loop.
