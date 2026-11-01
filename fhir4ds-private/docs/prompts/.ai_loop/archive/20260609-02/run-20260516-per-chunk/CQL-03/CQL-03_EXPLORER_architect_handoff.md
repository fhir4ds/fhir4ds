# Architect Handoff - CQL-03 EXPLORER

Phase: ARCHITECT
Status: Clean exit recommended

## Golden Standard

Golden standard written to `.temp/architect/golden_standard.md`. The relevant invariants are that CQL temporal/complex conversions are implemented once at the DuckDB macro/UDF boundary, translator lowering reuses that boundary, partial precision is preserved as a CQL value shape, JSON-shaped complex internals are structurally validated before numeric operations, and native-loaded versus forced Python fallback registrations stay parity-tested.

## Structural Audit

No new architectural findings. The remediation improves boundary integrity by removing duplicated temporal validation from translator SQL generation and routing Date/DateTime conversion through the public macro surface. Ratio fallback hardening is local to the Python UDF boundary and aligns it with native-loaded row-level NULL behavior. No C++ native source changed, so no extension rebuild/copy was required.

## QA Assessment

QA was sufficient for EXPLORER. It included weird compositions across translated definitions, direct DuckDB helpers, `convert`, temporal partial precision, invalid calendar values, JSON-shaped Ratio internals, and native-vs-forced-fallback comparison. No `RETRY_QA` veto.

## Issue Summary

- SPEC_VIOLATION: 1 resolved (`CQL03-EXPLORER-001`)
- BACKEND_PARITY: 1 resolved (`CQL03-EXPLORER-002`)
- New issues: 0

## Validation Reviewed

- Focused temporal/complex + expression tests: 151 passed
- Conversion/core parity subset: 5 passed
- Broad CQL pytest: 4899 passed, 5 skipped
- Official CQL compliance pytest: 3044 passed
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822
