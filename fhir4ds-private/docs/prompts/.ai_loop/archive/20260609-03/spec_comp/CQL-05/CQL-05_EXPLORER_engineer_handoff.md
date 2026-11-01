# Engineer Handoff — CQL-05 EXPLORER

## Issues Resolved

### QA-001

Root cause: `Children()`/`Descendants()` translation wrapped top-level
temporal/Long tuple values, but nested `TupleExpression` and `ListExpression`
values used ordinary translation. Once serialized into JSON, Date/Time values
looked like strings and Long values looked like integers to the structural
list UDFs.

Fix: `_translate_structural_traversal_value()` now recursively translates
nested tuples and lists for structural traversal, preserving the existing
`__fhir4ds_cql_type` transport markers for nested Date, DateTime, Time, and
Long values.

### QA-002

Root cause: `function_inliner.py` rebuilt `BinaryExpression` nodes during
substitution and nested-call inlining without copying `strict=True`, erasing
the parser distinction between `cast X as T` and nullable `X as T`.

Fix: all BinaryExpression cloning paths in the inliner now preserve
`strict=getattr(expr, "strict", False)`.

## Files Changed

- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/function_inliner.py`
- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`
- `.temp/qa/cql05_explorer_probe.py`
- `AGENTS.md`
- `extensions/cql/AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`

## Validation

- `python3 .temp/qa/cql05_explorer_probe.py`: passed
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py -q`: 11 passed
- Focused parser/conversion/primitive/structural subset: 106 passed
- Full conformance via `python3 conformance/scripts/run_all.py | grep ...`: 2822/2822
