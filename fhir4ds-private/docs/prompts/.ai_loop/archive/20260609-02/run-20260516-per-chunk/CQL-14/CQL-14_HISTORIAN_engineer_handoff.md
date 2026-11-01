# Engineer Handoff: CQL-14 HISTORIAN

## Triage

| Issue | Category | Severity | Status |
|---|---|---:|---|
| QA-001 | SPEC_VIOLATION | HIGH | RESOLVED |
| QA-002 | SPEC_VIOLATION | HIGH | RESOLVED |

## Fixes

QA-001 fixed a no-Python/browser-style C++ parity bug in `dateSubtractQuantity`. `ApplyQuantityAtInputPrecision()` preserved fractional weeks via millisecond arithmetic, so `dateSubtractQuantity('2024-01-15', '{"value":1.5,"unit":"week"}')` returned `2024-01-04`. The C++ week branch now truncates to an integer week count and applies `AddDays(dt, int_value * 7)`, matching forced Python fallback and native-loaded registration (`2024-01-08`).

QA-002 fixed one-argument `Time(hour)` translation. The translator previously shared the one-argument path with `time from <temporal>` extraction, so `Time(12)` returned `NULL`. A raw-AST pre-translate disambiguation now routes integer hour arguments and `DateComponent` hour expressions through component construction while preserving lowercase `time from @DateTime` extraction.

## Files Changed

- `extensions/cql/src/cql_extension.cpp`
- `fhir4ds/cql/translator/expressions/__init__.py`
- `fhir4ds/cql/translator/expressions/_temporal_components.py`
- `fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
- `extensions/cql/AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`

## Verification

```bash
cmake --build extensions/cql/build/release --target cql_loadable_extension -j2
cp extensions/cql/build/release/extension/cql/cql.duckdb_extension fhir4ds/cql/duckdb/extensions/cql.duckdb_extension
pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q --tb=short
```

Result: `10 passed`. Manual native-loaded, forced Python fallback, and C++-only translated probes confirmed `Time(12)`, `Time(hour from @T12:30)`, `time from @2024-01-01T12:30:15`, translated `@2024-01-15 - 1.5 weeks`, and direct C++ `dateSubtractQuantity(... 1.5 week)` all match expected outputs.
