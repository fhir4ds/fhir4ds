# Architect Handoff - FP-05 HISTORIAN

## Structural Health

Clean. No production code was changed in this HISTORIAN pass, and no new
architectural findings were opened. The fresh QA probe verifies the existing
FP-05 implementation across Python core/fallback and native DuckDB/C++ without
introducing new runtime paths.

## Audit Notes

The implementation remains aligned with the FP-05 golden standard: subsetting
functions enforce Integer/singleton boundaries, public DuckDB wrappers keep
row-resilient empty/NULL behavior for runtime errors, set helpers continue to
use FHIRPath equality semantics, and current `combine(other, preserveOrder)`
works in both backends. The fresh probe is correctly pinned to the workspace
root on `sys.path`, preventing installed-package drift from masquerading as
native/fallback behavior drift.

QA was sufficient. It covered every requested §5.3/§5.4 surface, invalid
index/count types, exact arity failures, multi-item `single()` row resilience,
duplicate-preserving vs duplicate-eliminating semantics, scoped collection
arguments inside `select()`, native C++ registration, and forced Python
fallback registration. No `RETRY_QA` flag was set.

## Issue Counts

- SPEC_VIOLATION: 0.
- API_CONTRACT: 0.
- DATA_HANDLING: 0.
- REGRESSION_RISK: 0.
- Open issues: 0.
- New architect findings: 0.

## Validation Reviewed

- `python3 .temp/qa/fp05_historian_fresh_probe.py` passed, 52 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py -q` passed, 11/11.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` passed, 9/9.
- Full conformance passed 2822/2822: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47.

## Recommended Fix Order

No further engineering work is required for FP-05 HISTORIAN.
