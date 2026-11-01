# QA Handoff - CQL-06 EXPLORER

## Scope

Abusive CQL-06 testing of conversion checks across native-loaded and forced Python fallback DuckDB registrations. Probed long numeric strings, leading-zero decimals, decimal overflow, scale overflow, malformed date/time strings, JSON quantity/ratio edge cases, unsupported UCUM units, translated CQL execution, and randomized invalid strings.

## Results

- Direct edge-case SQL probes had no native/fallback divergence.
- Translated CQL library covering every CQL-06 item passed 21 definitions on both registrations.
- Random string fuzzing passed 720 conversion-check calls with no native/fallback divergence or unexpected exceptions.
- Focused conversion parity pytest passed 13/13.

No new issues were found.
