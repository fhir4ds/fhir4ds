# QA Handoff: CQL-14 EXPLORER

## Scope

Chunk CQL-14: Date/Time Operators Part 2. EXPLORER pass stressed current-clock helpers, precision comparisons with timezone offsets, `Time(...)` trailing nulls, `TimeOfDay()` comparisons, DateTime minus Quantity, translated CQL, forced Python fallback, native-loaded DuckDB, and C++-only extension loading where available.

`docs/architecture/translator/AGENTS.md` is not present in this checkout; root `AGENTS.md`, `extensions/cql/AGENTS.md`, `GLOBAL_RULES.md`, `GLOBAL_KNOWLEDGE.md`, and `PROC_VALIDATION.md` were read.

## Findings

- `QA-001` HIGH SPEC_VIOLATION: DateTime precision comparisons normalize timezone offsets for year/month/day precision. The CQL Reference v1.5.3 Same As / Same Or Before / Same Or After rules limit offset normalization to hour, minute, second, and millisecond precision. Fresh probe: `.temp/qa/cql14_explorer_probe.py`.
- `QA-002` HIGH API_CONTRACT: forced Python fallback `cqlSameAsP` / related helpers raise `OverflowError` for offset-bearing `Time` values near midnight because the comparison path normalizes time-only values on year 1. Native C++ returns a Boolean; the public helper should be row-resilient and parity-aligned. Fresh probe: `.temp/qa/cql14_explorer_probe.py`.

## Expected Coverage

The same probe also guards the CQL-14 HISTORIAN regression (`Time(12, null)` -> `T12`, `Time(12, null, 0)` -> NULL), second-precision DateTime offset normalization, `TimeOfDay()` self-comparison, and fractional DateTime quantity subtraction.
