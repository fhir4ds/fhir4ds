# Engineer Handoff — CQL-06 HISTORIAN (iteration 1, 2026-08-20)

## Issues
- **QA-001 (HIGH, SPEC_VIOLATION) → RESOLVED**
  - Root cause: `QuantityToString` macro in `/mnt/d/fhir4ds/fhir4ds/cql/duckdb/macros/conversion.py` unconditionally wrapped the unit in single quotes. CQL 1.5 Appendix B §ToString (Table 9-G) gives the Quantity format `(-)?#0.0# (('<unit>')|(<unit>))` and states verbatim: "ToString(4 days) results in the string value `4 days` (i.e. not `4 'd'`)" — calendar-duration keywords must render bare; quoting is for UCUM units.
  - Fix: `QuantityToString` now renders units in the data-driven `_CQL_CALENDAR_DURATION_UNITS` registry (imported from `udf/quantity.py`) as bare keywords (`4 day`, `12 month`) and keeps UCUM units quoted (`5 'cm'`, `-0.1 'mg'`). Shared macro → both Python-supplement and native-supplemented backends fixed in one place; no C++ change needed (macro layer).
  - Round-trip preserved: `ToQuantity(ToString(4 days))` → quantity equal to source; `ToQuantity(ToString(5 'cm'))` likewise.

## Verification
- Reproducer re-run on both backends: `ToString(4 days)` → `4 day` (bare), UCUM unchanged. Probe: `.temp/qa/cql06_historian_2026_08_20/`.
- Focused regression test added: `test_cql_to_string_renders_calendar_duration_keywords_bare_cql06_historian` in `fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py` — file 9/9 passed.
- Adjacent suites: `test_conversion_function_parity.py` + `test_macros_tier1.py` 79/79 passed.
- Baselines: full conformance 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47). No regression.

## Files changed
- `fhir4ds/cql/duckdb/macros/conversion.py` (QuantityToString calendar-keyword branch)
- `fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py` (new regression test)

## New issues discovered
None. (Verified non-issue: integer literals >2^31-1 without `L` suffix correctly fail translation; CQL 1.5 requires the Long `L` suffix.)
