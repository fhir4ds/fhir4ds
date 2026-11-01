# Engineer Handoff - FP-05 SKEPTIC

## Issue Status

- `QA-001` RESOLVED: `combine(other, preserveOrder)` was missing in both
  native DuckDB/C++ and forced Python fallback.

## Root Cause

Both backends still modeled FHIRPath §5.4 `combine()` as exactly one argument.
The current official signature is
`combine(other : collection, [preserveOrder : Boolean]) : collection`, so
`combine(B, true)` must be valid. Native `Evaluator::evalFunction()` rejected
two-argument `combine` at arity validation; Python core did the same through
`invocation_registry`.

## Fix

- Updated Python core `combine` arity to accept one or two parameters.
- Added singleton Boolean validation through the existing parameter machinery.
- Preserved existing duplicate-retaining append behavior; when `preserveOrder`
  is `true`, that append behavior is the specified order-preserving result.
- Updated native C++ dispatch to allow two args for `combine` only and validate
  the optional argument as a singleton Boolean.
- Rebuilt and copied `fhirpath.duckdb_extension`.
- Added focused Python/native parity tests and native sqllogictest assertions.

## Validation

- `python3 .temp/qa/fp05_skeptic_fresh_probe.py` passed, 50 cases.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py -q` passed, 11/11.
- `./build/release/test/unittest "*fhirpath*"` passed, 756 assertions.
- Full conformance summary passed: ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes For Architect

The only subtle boundary is `fhirpath_is_valid()` for dynamic second arguments
such as `a.combine(b, ints)`: the expression is syntactically/functionally
valid, while a row with non-Boolean `ints` returns empty/NULL through public
row-resilient UDFs. Literal non-Boolean arguments like `combine(b, 1)` remain
invalid.
