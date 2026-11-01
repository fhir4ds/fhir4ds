# Engineer Handoff - CQL-17 HISTORIAN

## Issue Resolved

`QA-001` HIGH: closed typed-null interval bounds leaked internal sentinels or used DateTime extrema rather than point-type extrema for `start of` / `end of`.

## Root Cause

Python `intervalStart` / `intervalEnd` returned raw closed bounds before interpreting the translator's `__null__` sentinel. The no-Python C++ `IntervalStartFunc` / `IntervalEndFunc` did interpret absent typed-null bounds, but always returned DateTime minimum/maximum constants regardless of the interval point type.

## Fix

- Python interval helpers now ignore `__null__` as a public raw bound and derive closed-null extrema from the finite peer bound.
- C++ no-Python interval helpers now derive extrema by `Interval.bound_type`.
- Open null boundaries still return SQL NULL.
- Quantity typed-null extrema are left unsupported/NULL rather than guessing a non-spec minimum/maximum.

## Changed Files

- `fhir4ds/cql/duckdb/udf/interval.py`
- `extensions/cql/src/cql_extension.cpp`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py`
- `.temp/qa/cql17_historian_probe.py`
- `AGENTS.md`
- `extensions/cql/AGENTS.md`

## Validation

- Fresh probe: `.temp/qa/cql17_historian_probe.py` passed.
- Focused CQL-17 parity: `3 passed`.
- Interval part 1/2/3 + WASM/no-Python gates: `31 passed`.
- Official CQL interval operator category: `412 passed`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.
