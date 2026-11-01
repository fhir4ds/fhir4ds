# Engineer Handoff — CQL-06 SKEPTIC (iteration 1)

## Issues
- **QA-001 (HIGH, SPEC_VIOLATION) → RESOLVED**
  - Root cause: `toQuantity` in `/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/quantity.py` matched only `(?:\s*'([^']+)')?` for the unit designator — quoted UCUM only. CQL 1.5 Appendix B §ToQuantity also admits a bare "calendar duration keyword, singular or plural" as the unit designator, and Table 9-G's round-trip rule (`ToString(4 days)` → `4 days`) requires ToQuantity to parse that form.
  - Fix: unit alternative extended to `(?:\s*(?:'([^']+)'|(\S+)))?` with the bare token gated on the existing data-driven `_CQL_CALENDAR_DURATION_UNITS` registry (case-sensitive: 'Years' still rejected). Bare non-calendar UCUM ('5 mg') stays rejected per the spec's case-sensitive string-literal requirement for UCUM.
  - Affected surfaces repaired: ToQuantity, ConvertsToQuantity, ToRatio, ConvertsToRatio (ratio quantities reuse the quantity grammar). Both Python-supplement and native-supplemented backends share this code path — parity confirmed.

## Verification
- Reproducer (10 cases incl. negatives): PASS on both backends (`.temp/qa/cql06_skeptic/`).
- Focused regression test added: `test_cql_to_quantity_accepts_bare_calendar_duration_keywords_cql06_skeptic` in `fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py` — file: 8/8 passed.
- Baselines: CQL conformance 1706/1706 (100%); DQM 47/47 (100%). No regression.

## Files changed
- `fhir4ds/cql/duckdb/udf/quantity.py` (toQuantity grammar)
- `fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py` (new regression test)

## New issues discovered
None.
