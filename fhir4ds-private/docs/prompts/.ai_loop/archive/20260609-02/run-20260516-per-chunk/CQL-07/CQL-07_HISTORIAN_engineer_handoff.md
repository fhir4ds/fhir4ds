# CQL-07 HISTORIAN Engineer Handoff

## Completed Fix

Resolved `QA-001`: translated CQL `ToString(Ratio)` and `convert Ratio to
String` returned implementation Ratio JSON instead of the CQL-required
`<quantity>:<quantity>` representation.

## Code Changes

- Added Python fallback `RatioToString` in `fhir4ds/cql/duckdb/udf/ratio.py`.
- Added native C++ `cql::ratio_to_string` and registered `RatioToString` in
  `extensions/cql/src/cql_extension.cpp`.
- Exported C++ quantity unit validation so Ratio string formatting rejects
  invalid quantity components.
- Routed statically-known Ratio operands in the CQL translator through
  `RatioToString`.
- Refreshed the bundled CQL extension binary.

Bundled CQL extension SHA256:
`1b9a6c253a816f6d137a551a1d0ee961b92070cef9cebf9c7bf7aacb8d75bac0`

## Verification

- Python ratio UDF tests: 35/35 passed.
- Focused CQL-07 parity pytest: 22/22 passed.
- Native CQL extension SQL tests: 624 assertions passed.
- Full `fhir4ds/` pytest: 7154 passed, 5 skipped, 9 warnings.
- Serial full conformance: 2822/2822 passed.
