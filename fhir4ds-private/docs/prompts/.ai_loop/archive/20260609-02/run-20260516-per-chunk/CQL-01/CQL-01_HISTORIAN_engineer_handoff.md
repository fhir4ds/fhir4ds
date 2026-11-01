# Engineer Handoff — CQL-01 HISTORIAN

## Issue Status
- `QA-001`: RESOLVED.

## Root Cause
- `fhir4ds/cql/translator/expressions/_operators.py` handled binary `as` by returning the left operand unchanged for all non-Quantity targets.
- That made primitive `as` behave like conversion/pass-through instead of CQL's runtime type assertion.

## Fix
- Added primitive-target handling for binary `as`.
- Matching primitive literals return the original SQL expression.
- Mismatched primitive literals lower to `SQLNull()`.
- `as Any` preserves the input.
- Literal and known conversion-function mismatches lower to `SQLNull()`.
- Dynamic FHIR/measure values use primitive shape guards plus `TRY_CAST` so matching runtime values become typed SQL results while mismatches return NULL.

## Tests Added
- Extended `fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py` with translation assertions for primitive `as` and native-loaded/forced-fallback execution parity.

## Validation
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py -q` — 5 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py -q` — 7 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_cql.py` — 1706/1706 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql fhir4ds/cql/duckdb/tests -q --tb=short` — 507 passed, 5 skipped.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/tests/unit fhir4ds/cql/tests/integration -q --tb=short` — 1297 passed.
- Architect follow-up: targeted DQM rerun for CMS771/CMS0334 passed 2/2 at 100% after adjusting dynamic casts.
- Architect follow-up: full conformance passed 2822/2822.
- Architect follow-up: broad CQL unit/integration/DuckDB integration pytest passed 1359 with 5 skips.

## Memory Updates
- Added CQL primitive `as` assertion guidance to root `AGENTS.md`.
- Added CQL extension/package guardrail to `extensions/cql/AGENTS.md`.
