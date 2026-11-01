# CQL-13 HISTORIAN Engineer Handoff

## Code Changes

Primary files:

- `fhir4ds/cql/translator/expressions/_temporal_components.py`
- `fhir4ds/cql/duckdb/udf/datetime.py`
- `fhir4ds/cql/duckdb/tests/integration/test_datetime_part1_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py`

## Implementation Notes

- One-argument `Date(...)` remains overloaded: integer literals are Date constructors, string/nonliteral values are date extraction. Decimal and Boolean literal constructor components now raise.
- `date from DateTime(...)` strips the DateTime marker and returns the date precision actually present before `T`.
- Python fallback timezone suffix validation now matches the C++ bound: `Z` or `+/-HH:MM`, maximum absolute offset `14:00`.
- The timezone guard deliberately ignores non-temporal strings such as JSON interval payloads and URNs; an earlier broad colon check regressed DQM until narrowed to actual time-looking strings.

## Current State

All HISTORIAN issues are resolved and verified. No open engineering blockers remain for CQL-13 HISTORIAN.
