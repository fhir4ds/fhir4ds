# Engineer Handoff — FP-11 HISTORIAN

## Issues Resolved
- `QA-FP11-HIST-001` (HIGH): Fixed native C++ `round(precision)` decimal serialization by storing formatted `source_text` on precision-bearing Decimal results. Rebuilt and copied `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
- `QA-FP11-HIST-002` (MEDIUM): Fixed exported direct helper `round_fn()` to use FHIRPath half-away-from-zero rounding and reject invalid precision.

## Files Changed
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/duckdb/functions/math.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py`
- `fhir4ds/fhirpath/duckdb/tests/unit/test_math.py`
- `AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.ai_loop` state/handoff files

## Verification
- Direct helper reproducers: `round_fn(2.5) -> [3]`, `round_fn(-2.5) -> [-3]`, `round_fn(2.55, 1) -> [2.6]`, invalid precision returns `[]`.
- Native DuckDB reproducer: `3.14159.round(3)` returns `(['3.142'], '3.142', '[3.142]')`.
- `extensions/fhirpath/build/release/test/unittest '*fhirpath*'` => 214 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_math.py -q` => 103 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests -q` => 1028 passed, 1 pre-existing warning.
- `python3 conformance/scripts/run_all.py | grep ...` => final rerun: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes for Architect
- Scope stayed within §5.7 rounding behavior and tests.
- No new issues discovered during remediation.
