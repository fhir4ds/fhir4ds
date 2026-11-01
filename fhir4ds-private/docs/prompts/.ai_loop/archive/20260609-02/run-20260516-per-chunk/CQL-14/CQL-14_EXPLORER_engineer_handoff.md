# Engineer Handoff: CQL-14 EXPLORER

## Triage

| Issue | Category | Severity | Status |
|---|---|---:|---|
| QA-001 | SPEC_VIOLATION | MEDIUM | RESOLVED |

## Fix

`dateSubtractQuantity` in the Python fallback treated missing Quantity `value` as zero and raised `InvalidInputException` for null or non-numeric values. This diverged from the no-Python C++ public helper, which returns SQL `NULL` for invalid Quantity payloads.

I added `_parse_date_quantity_payload()` in `fhir4ds/cql/duckdb/udf/datetime.py` and routed both `dateAddQuantity` and `dateSubtractQuantity` through it. The helper accepts only object-shaped JSON with a finite numeric JSON `value` and string `unit` or `code`; malformed JSON, missing/null/string/Boolean/non-finite values, huge values beyond the C++ public-helper guardrails, and invalid units now return `None` at the public SQL boundary. Valid Quantity arithmetic that overflows the accepted CQL date range still raises, preserving official invalid-expression conformance.

## Files Changed

- `fhir4ds/cql/duckdb/udf/datetime.py`
- `fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`

## Verification

```bash
python3 .temp/qa/cql14_explorer_probe.py
pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q --tb=short
python3 conformance/scripts/run_cql.py | grep -E "CqlDateTimeOperatorsTest.xml|Summary|FAIL|ERROR"
python3 conformance/scripts/run_all.py
python3 -m pytest -q --tb=short
```

Results: EXPLORER probe `failures=0`; focused pytest `10 passed`; CQL conformance `1706/1706` with `CqlDateTimeOperatorsTest.xml` at `317/317`; repeat full conformance `2822/2822`; full pytest `7190 passed, 5 skipped, 9 warnings`.
