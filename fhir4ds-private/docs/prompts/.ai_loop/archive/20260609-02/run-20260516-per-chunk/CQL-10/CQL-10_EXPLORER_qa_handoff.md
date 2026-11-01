# QA Handoff: CQL-10 EXPLORER

## Scope

CQL Arithmetic Operators Part 1: `Abs`, `Add`, `Ceiling`, `Divide`, `Floor`,
`Exp`, `HighBoundary`, `Log`, `Ln`, and `LowBoundary`.

EXPLORER reran the chunk independently from source and tests, without reading
archived prior workflow outputs. The pass targeted official XML coverage,
dynamic FHIR operands, public DuckDB helper calls, generated SQL execution,
native-loaded C++ registration, C++-only/browser extension surface, and forced
Python fallback registration.

## Issues Closed

- `QA-CQL10-EXPLORER-001`: C++/Python boundary helper divergence for exponent
  numeric text, invalid temporal strings, and DateTime timezone suffixes.
- `QA-CQL10-EXPLORER-002`: C++-only `dateAddQuantity` accepted invalid
  temporal/Quantity inputs and missed fractional DateTime day/week arithmetic.
- `QA-CQL10-EXPLORER-003`: Quantity/scalar NULL arithmetic produced Quantity
  JSON with `"value": null` instead of SQL NULL.
- `QA-CQL10-EXPLORER-004`: One-argument `Log` and Date +/- Integer generated
  binder-failing SQL despite accepted translator paths.

## Verification

- Native C++ extension rebuilt and copied into the Python package.
- Native C++ CQL unittest: 638 assertions passed.
- Focused arithmetic/C++ surface parity pytest: 18 passed.
- Official CQL conformance: 1706/1706.
- Full conformance: 2822/2822.
- Full `fhir4ds` pytest: 7172 passed, 5 skipped, 9 warnings.

## Residual Risk

No open CQL-10 EXPLORER issues remain. Keep future arithmetic changes covered
across forced Python fallback, native-loaded C++ DuckDB, and C++-only/browser
helper calls because several failures existed only on direct public helpers.
