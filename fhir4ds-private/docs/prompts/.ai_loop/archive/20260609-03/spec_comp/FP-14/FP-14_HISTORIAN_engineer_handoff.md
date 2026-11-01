# Engineer Handoff - FP-14 HISTORIAN

Issue handled: `QA-001`

## Fix

The forced Python fallback comparison path now treats Time-only values as a separate comparison domain from Date and DateTime values. This prevents expressions such as `@2018-01-01 < @T10:00:00` and `@2018-01-01T00:00:00 < @T10:00:00` from producing definitive Boolean results.

Changed:
- `fhir4ds/fhirpath/engine/invocations/equality.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`

## Spec Reference

FHIRPath Normative Release Section 6.2 defines comparison operands as singleton values of the same type or implicitly convertible types. It defines Date, DateTime, and Time comparison within their own temporal domains, with precision uncertainty returning empty.

## Validation

- Fresh QA probe after fix: 44 cases, 0 native/fallback mismatches, 0 expectation failures.
- Focused comparison parity: 9 passed.
- Related equality/arithmetic parity: 37 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No new issues were discovered during remediation.
