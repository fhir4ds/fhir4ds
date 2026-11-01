# Engineer Handoff: CQL-06 / EXPLORER

## Resolved Issues

`QA-001` HIGH resolved.

Root cause: CQL `ToString` used a generic DuckDB `CAST(... AS VARCHAR)`, and
translated generic `ToString` bypassed the public macro with `SQLCast`. The
`ConvertsToString` Python UDF also returned true for every non-null value, so
CQL List and Tuple values were treated as String-convertible.

Fix:

- Added structural type guards to public `ToString` and `ConvertsToString`
  macros for DuckDB List, Struct, Map, and JSON values.
- Stopped registering the broad Python `ConvertsToString` UDF over the macro.
- Hardened the Python helper for direct list/dict/tuple inputs.
- Routed generic translated `ToString` through the public macro.
- Preserved existing `QuantityToString` and `RatioToString` special routing.
- Added focused parity coverage for direct helper calls and translated CQL.

## Validation

```bash
python3 .temp/qa/cql06_explorer_probe.py
python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py fhir4ds/cql/duckdb/tests/test_macros_tier1.py fhir4ds/cql/tests/unit/test_v2_expressions.py -q
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > validation_summary.log && cat validation_summary.log
```

Results:

- Fresh probe passed.
- Focused tests: 225 passed.
- Full conformance: 2822/2822.

## Changed Files

- `fhir4ds/cql/duckdb/macros/conversion.py`
- `fhir4ds/cql/duckdb/udf/conversion.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py`
- `fhir4ds/cql/tests/unit/test_v2_expressions.py`
- `.temp/qa/cql06_explorer_probe.py`
- `AGENTS.md`
- `extensions/cql/AGENTS.md`
