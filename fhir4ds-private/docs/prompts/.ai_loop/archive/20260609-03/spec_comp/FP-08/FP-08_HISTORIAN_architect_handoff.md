# Architect Handoff: FP-08 HISTORIAN

Status: CLEAN.

Audit result:
- `QA-001` HIGH is resolved with no remaining non-terminal FP-08 issues.
- The fix stayed inside the FP-08 conversion boundary: native C++ Quantity
  materialization/stringification, Python fallback Quantity parsing/conversion,
  and focused parity tests.
- No `RETRY_QA` is required. `min_iterations=1` is satisfied at iteration 1.

Validation reviewed:
- `.temp/qa/fp08_historian_probe_after_fix.log`: `cases=39`,
  `mismatches=0`, `failures=0`.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q`:
  `18 passed`.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath`:
  `424` native assertions passed.
- `python3 conformance/scripts/run_all.py`: `2822/2822` overall.

Architecture notes:
- Resource-backed FHIR Quantity values must be materialized before
  `toQuantity()`, `convertsToQuantity()`, `toString()`, and
  `convertsToString()` decisions. Literal-only Quantity handling is not enough
  for FP-08 compliance.
- Quantity-like JSON is valid only with a finite numeric `value` and a string
  `code` or `unit`; malformed shapes must produce empty/NULL row resilience at
  public DuckDB boundaries.
- Compatible unit conversions such as `mg` to `g` must preserve fractional
  quantities.

Exit:
- Set `workflow` to `null`.
- Set `exit_reason` to `CLEAN`.
