# Engineer Handoff - CQL-12 SKEPTIC

## Issue Resolved

`QA-001` HIGH: CQL string operators silently coerced non-string operands through
DuckDB string behavior.

## Root Cause

The translator emitted raw SQL for statically invalid string expressions and
the public macros used DuckDB `||` / `array_to_string` directly. DuckDB accepts
some numeric operands at those boundaries, so invalid CQL such as
`Concatenate(1, 'x')`, `1 & 'x'`, and `Combine({1, 2})` became valid SQL output.

## Fix

- Added public macro guards:
  - `Concatenate` / `Concat` require `VARCHAR` operands.
  - `Combine` / `CombineSep` require `VARCHAR[]` or null-list input.
  - `CombineSep` requires a string separator when the separator is non-null.
  - Typed SQL nulls such as `CAST(NULL AS INTEGER)` and
    `CAST(NULL AS INTEGER[])` are rejected rather than bypassing type checks.
- Added translator validation for statically known string operands:
  - Function calls including `Combine`, `Concatenate`, `StartsWith`,
    `EndsWith`, `Matches`, `ReplaceMatches`, `Split`, `SplitOnMatches`,
    `PositionOf`, `LastPositionOf`, `Substring`, `Indexer`, `Lower`, and
    `Upper`.
  - Binary string operators `&` and mixed string `+`.
- Added regression coverage in
  `fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py`.

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/cql12_skeptic_probe.py` passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py -q`:
  5 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py -k CqlStringOperatorsTest -q`:
  162 passed, 2882 deselected.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/test_macros_tier1.py fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py -q`:
  70 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  overall 2822/2822.

## Changed Files

- `fhir4ds/cql/duckdb/macros/string.py`
- `fhir4ds/cql/duckdb/macros/list.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql12_skeptic_probe.py`
