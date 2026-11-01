# Engineer Handoff - CQL-11 HISTORIAN

## Issues Resolved

- `QA-001` HIGH: CQL `Round` negative half ties used `floor(x + 0.5)` semantics and returned `0` for `Round(-0.5)`.
- `QA-002` HIGH: CQL `Round` null precision did not default to `0` on the direct SQL macro/native helper surfaces.

## Fixes

- Updated Python fallback `mathRound` to use sign-aware traditional rounding.
- Updated SQL macros `Round` and `RoundTo`; `RoundTo` now treats NULL precision as `0`.
- Updated native C++ `cql::math_round` and `MathRoundFunc`; the native UDF now accepts NULL precision as `0`.
- Rebuilt `extensions/cql/build/release/extension/cql/cql.duckdb_extension` and copied it to `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.
- Updated local CQL arithmetic conformance XML expectations for `Round(-0.5)` and `Round(-1.5)` to match the current CQL Reference examples/prose.
- Added focused parity coverage for Python fallback, native-loaded, and no-Python/browser-style surfaces.

## Validation

- Fresh probe: `.temp/qa/cql11_historian_probe.py` PASS.
- Focused pytest: `test_arithmetic_part2_parity.py`, `test_wasm_cpp_surface.py`, `test_wasm_translate_execute_gate.py` — 15/15 passed.
- Macro pytest: `test_macros_tier1.py` — 67/67 passed.
- CQL conformance: 1706/1706 passed.
- Full conformance: 2822/2822 passed.

## Notes

- The current CQL Reference says `Round(-0.5) // -1` and null precision defaults to `0`; the bundled XML had stale expectations for the two negative half cases and was updated to preserve the release gate against the current normative text.
