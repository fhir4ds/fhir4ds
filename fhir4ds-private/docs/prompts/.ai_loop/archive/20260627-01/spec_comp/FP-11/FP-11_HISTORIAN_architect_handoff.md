# Architect Handoff - FP-11 HISTORIAN

Structural audit closed cleanly for FP-11 HISTORIAN. Fresh QA covered every
current FHIRPath §5.7 Math function across native DuckDB/C++ and forced Python
fallback paths, including dynamic arguments, resource-backed Quantity JSON,
Integer/Long boundaries, and Decimal-shaped `power()` / `toString()` behavior.
The three MEDIUM SPEC_VIOLATION issues were fixed without adding fixture
special cases: native integral math now avoids `double` at 64-bit boundaries,
fallback Quantity recognition reuses shared `util.parse_value(...)` conversion,
and fallback Decimal string rendering preserves the required fractional digit.
No new architecture findings were opened, no `RETRY_QA` was set, and review-10
open findings did not intersect this chunk.

Issue counts by category:
- SPEC_VIOLATION: 3 VERIFIED.

Recommended fix order:
- None. All FP-11 HISTORIAN issues are terminal and verified.

Validation:
- `python3 .temp/qa/fp11_historian_fresh_probe.py` passed, 48 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py -q` passed, 7/7.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q` passed, 23/23.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_math.py -q` passed, 105/105.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py -q` passed, 113/113.
- `cmake --build extensions/fhirpath/build/release --config Release -j 8` passed.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"` passed, 874 assertions.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` passed: 2822/2822 overall.
