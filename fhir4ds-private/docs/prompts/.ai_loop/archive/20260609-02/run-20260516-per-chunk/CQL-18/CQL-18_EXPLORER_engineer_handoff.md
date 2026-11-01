# Engineer Handoff - CQL-18 EXPLORER

## Issue Status

- `QA-001`: RESOLVED.

## Fix

- Updated `CQLListElementEqual` mixed numeric comparison from `DOUBLE` equality to exact `DECIMAL(38,8)` equality.
- Updated translated scalar decimal-literal equivalence to round `DECIMAL(38,8)` operands with `system.round(...)`, avoiding both floating precision collapse and the public CQL `Round(x)` macro binder.

## Files Changed

- `fhir4ds/cql/duckdb/macros/list.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py`
- `fhir4ds/cql/duckdb/tests/test_list_udfs.py`
- `extensions/cql/AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/deep_research_findings.md`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`
- `fhir4ds-private/docs/prompts/.ai_loop/qa_handoff.md`

## Validation

- Fresh EXPLORER probe: passed across forced Python fallback, native-loaded registration, and no-Python/browser-style C++.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py fhir4ds/cql/duckdb/tests/test_list_udfs.py -q --tb=short` -> 51 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py fhir4ds/cql/duckdb/tests/test_list_udfs.py -q --tb=short` -> 54 passed.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_list_operators -q --tb=short` -> 212 passed.
- `python3 conformance/scripts/run_all.py` -> 2822/2822 overall, 100%.
- `python3 -m pytest -q --tb=short` -> 7213 passed, 5 skipped, 9 warnings.

## Notes For Architect

- The initial direct helper fix was incomplete because literal-list equivalence decomposes to scalar equivalence. The required deep-research report was appended before the second translator change.
- No C++ extension rebuild was needed; affected public no-Python/browser behavior is supplied through shared SQL macros and translator output.
