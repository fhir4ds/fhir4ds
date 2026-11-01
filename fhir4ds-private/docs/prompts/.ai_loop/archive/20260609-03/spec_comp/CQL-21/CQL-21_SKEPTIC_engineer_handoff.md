# CQL-21 SKEPTIC Engineer Handoff

## Remediation

Resolved `CQL21-SKEPTIC-001`.

Root cause: Python fallback registration and native-loaded supplement
registration masked stale/missing compiled-extension clinical age registrations.
The built no-Python C++ extension had the required sub-day `AgeIn*At` and
`CalculateAgeIn*At` functions after rebuild, but the bundled package extension
was stale and still lacked `AgeInHoursAt`, `AgeInMinutesAt`, and
`AgeInSecondsAt`.

Fix:

- Kept the C++ extension registration surface aligned for
  `AgeInHoursAt`, `AgeInMinutesAt`, `AgeInSecondsAt`,
  `CalculateAgeInHoursAt`, `CalculateAgeInMinutesAt`, and
  `CalculateAgeInSecondsAt`.
- Synced the rebuilt `cql.duckdb_extension` into
  `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.
- Extended no-Python clinical parity coverage to include the sub-day
  `CalculateAgeIn*At` functions.
- Recorded the CQL-21 no-Python clinical operator invariant in
  `extensions/cql/AGENTS.md`.

## Validation

- `python3 .temp/qa/cql21_skeptic_probe.py`: PASS across Python fallback,
  native-loaded, and no-Python paths.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py -q --tb=short`:
  9 passed.
- Direct package-extension load check: no missing sub-day age-at functions;
  `AgeInHoursAt` and `CalculateAgeInHoursAt` both returned `1`.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  OVERALL 2822/2822.

## Files

- `extensions/cql/src/cql_extension.cpp`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
- `fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py`
- `extensions/cql/AGENTS.md`
