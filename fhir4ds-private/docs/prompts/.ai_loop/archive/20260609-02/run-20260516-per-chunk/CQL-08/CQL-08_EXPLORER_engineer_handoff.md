# Engineer Handoff - CQL-08 EXPLORER

Phase: FIX

## Issues Resolved

### QA-001 - Infix `is true` / `is false` SQL truthiness

Root cause: the unary CQL operators lowered to DuckDB `IS TRUE` / `IS FALSE`. That made static non-Boolean inputs such as `1`, `0`, and `'true'` evaluate using SQL truthiness instead of CQL Boolean-only nullological semantics. Direct `IsTrue()` / `IsFalse()` calls also needed Boolean-context translation for dynamic FHIR Boolean paths, because those values can otherwise be transported as `VARCHAR`.

Fix:
- Infix `is true` / `is false` now lower to `IsTrue(expr)` / `IsFalse(expr)`.
- `is not true` / `is not false` now lower to `NOT IsTrue(expr)` / `NOT IsFalse(expr)`.
- These unary paths translate operands with `boolean_context=True`, so FHIR Boolean properties use `fhirpath_bool`.
- Direct `IsTrue()` / `IsFalse()` FunctionRef translation now also translates its single argument in Boolean context.

### QA-002 - Invalid `Coalesce` scalar arities

Root cause: `_translate_coalesce()` accepted any scalar argument count and lowered directly to SQL `COALESCE`.

Fix:
- Scalar `Coalesce` now requires 2 through 5 arguments.
- Single-list overload remains valid, including empty/all-null lists.
- Invalid scalar calls raise `TranslationError`.

## Tests Run

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py -q`
  - `6 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py fhir4ds/cql/tests/unit/test_v2_expressions.py -q`
  - `162 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py`
  - ViewDefinition `134/134`
  - FHIRPath R4 `935/935`
  - CQL `1706/1706`
  - DQM `47/47`
  - Overall `2822/2822`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/ -x --tb=short`
  - `7160 passed, 5 skipped, 9 warnings`

## Files Changed

- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py`
- `extensions/cql/AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`
- `fhir4ds-private/docs/prompts/.ai_loop/qa_handoff.md`
- `fhir4ds-private/docs/prompts/.ai_loop/engineer_handoff.md`
