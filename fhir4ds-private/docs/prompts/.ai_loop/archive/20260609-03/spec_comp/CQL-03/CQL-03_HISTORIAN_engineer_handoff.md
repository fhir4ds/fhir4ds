# Engineer Handoff — CQL-03 HISTORIAN

## Fixed

Resolved `QA-001` in
`fhir4ds/cql/translator/expressions/_temporal_components.py`.

Root cause:
- The DateTime constructor literal fast path split Decimal timezone offsets
  into integer hours plus rounded fractional minutes without carrying
  `minute == 60`.
- Static Boolean offsets were accepted because Python `bool` is an `int`.
- Non-numeric static offsets could be ignored, producing a DateTime without the
  authored timezone component.

Remediation:
- Added static timezoneOffset validation for Decimal numeric literals only.
- Formatted offsets through rounded total minutes, then derived `hh:mm` with
  carry.
- Enforced the `+/-14:00` limit after total-minute rounding.
- Applied the same total-minute formatting and range guard to the runtime
  timezone path with `TRY_CAST`.

## Regression Coverage

Updated:
- `fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py`
- `.temp/qa/cql03_historian_probe.py`
- `AGENTS.md`
- `extensions/cql/AGENTS.md`

## Validation

- `python3 .temp/qa/cql03_historian_probe.py`: passed
- Focused pytest:
  `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/test_ratio_udfs.py -q`
  passed, 53 tests.
- Full conformance:
  `ViewDefinition 134/134`, `FHIRPath 935/935`, `CQL 1706/1706`,
  `DQM 47/47`, overall `2822/2822`.
