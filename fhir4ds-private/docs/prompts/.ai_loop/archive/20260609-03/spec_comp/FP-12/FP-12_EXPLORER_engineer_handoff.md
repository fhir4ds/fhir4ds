# Engineer Handoff - FP-12 EXPLORER

## Issues Resolved

- `QA-001` MEDIUM: `descendants()` accumulated every recursive child instead
  of honoring §5.8.2 shorthand equivalence with `repeat(children())`.
- `ARCH-001` MEDIUM: the first native fix still diverged for equal complex JSON
  objects with different key order.
- `ARCH-002` MEDIUM: native `descendants()` silently stopped at depth 100,
  while fallback continued through deeper valid descendants.

## Fix

- Python fallback `descendants()` now uses repeat-style "new item" tracking.
- Native C++ `descendants()` now uses repeat-style de-duplication with canonical
  JSON repeat keys. Object keys are sorted recursively so equal complex JSON
  values with different key order de-duplicate consistently.
- Native C++ no longer imposes a fixed 100-level `descendants()` traversal
  limit; it keeps the existing result-size safety guard.
- Added parity coverage for duplicate primitive/complex descendants and
  ordered-key complex objects plus a 105-level nested resource.
- Updated native sqllogictest coverage and duplicate-null descendant count
  expectations.
- Rebuilt and copied the native extension to
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

## Validation

- Fresh EXPLORER probe after deep fix: 43 cases, 0 mismatches, 0 failures.
- Focused pytest: `9 passed`.
- Native FHIRPath sqllogictest: `532 assertions passed`.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

No new issues were discovered after the retry fix.
