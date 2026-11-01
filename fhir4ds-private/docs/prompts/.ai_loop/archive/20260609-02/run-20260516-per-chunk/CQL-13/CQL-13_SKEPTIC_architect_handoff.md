# CQL-13 SKEPTIC Architect Handoff

## Result

CQL-13 SKEPTIC passed with 8 issues found, fixed, and verified. There are 0 open issues.

## Architectural Rules Reinforced

- Duration/difference helper outputs are public scalar-or-interval strings. Consumers must not rely on implicit DuckDB casts.
- Comparisons over duration/difference outputs should route through `cqlUncertainCompare`.
- Numeric consumers (`Truncate`, `/`, `div`, aggregate list math) must use explicit `TRY_CAST` only at numeric boundaries.
- Static CQL expressions that are definitely uncertainty intervals must keep official invalid behavior where the XML suite marks the operation invalid.
- DateTime marker precision is semantic. Preserve marker forms in constructors, public helpers, native formatting, and arithmetic.
- Public direct SQL helper behavior must be parity-tested across forced Python fallback, native-loaded registration, and no-Python C++/browser-style registration where applicable.

## Regression Gates

The SKEPTIC archive is supported by:

- Focused native/Python parity pytest: 10 passed.
- Targeted CMS0334 DQM: 135/135, 100%.
- DQM conformance: 47/47.
- Official CQL conformance: 1706/1706.
- Unified conformance: 2822/2822.
- Full package pytest: 7180 passed, 5 skipped.
- Native C++ CQL SQL runner: 694 assertions passed.
- `git diff --check`: clean.

## Next Personality

Proceed to CQL-13 HISTORIAN. Suggested emphasis:

- Historical partial DateTime edge cases around marker parsing and precision comparisons.
- Boundary interactions between `DurationBetween`, `DifferenceBetween`, and query/DQM generated SQL.
- Public helper parity for no-Python C++ surfaces that are easy to miss when translated CQL passes.
