# Engineer Handoff - FP-07 SKEPTIC

## Resolved Issues

`QA-001` RESOLVED: Added exact zero-argument enforcement for
`toDecimal()`, `toDate()`, `toDateTime()`, `convertsToDecimal()`,
`convertsToDate()`, and `convertsToDateTime()` across native C++ and forced
Python fallback.

`QA-002` RESOLVED: Native `toDecimal()` now parses decimal text only when the
effective input type is String. Temporal values such as `@2015` no longer
fall through through `toString()` and match the decimal regex.

`QA-003` RESOLVED: Forced Python fallback `toDate()` and `toDateTime()` now
handle already-typed `FP_Date` and `FP_DateTime` literal objects.

`QA-004` RESOLVED: Forced Python fallback `toDecimal()` raises
`FHIRPathError` for multi-item input and returns empty only for empty input,
matching native `fhirpath_is_valid()` behavior.

## Files Changed

- `fhir4ds/fhirpath/engine/invocations/__init__.py`
- `fhir4ds/fhirpath/engine/invocations/misc.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

## Validation

- FP-07 probe: 59 cases, 0 native/fallback mismatches
- Focused pytest: `test_conversion_parity.py` 16 passed
- Native FHIRPath sqllogictest: 402 assertions passed
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822

## Notes

No new issues discovered during remediation. The rebuilt native extension was
copied into `fhir4ds/fhirpath/duckdb/extensions/` and its SHA-256 matched the
release build artifact.
