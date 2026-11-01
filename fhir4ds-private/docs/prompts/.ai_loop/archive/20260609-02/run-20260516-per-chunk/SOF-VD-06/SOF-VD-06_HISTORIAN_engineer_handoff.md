# Engineer Handoff: SOF-VD-06 HISTORIAN

## Triage

| Issue | Category | Status | Resolution |
|---|---|---|---|
| QA-001 | SPEC_VIOLATION | RESOLVED | Parser and direct dataclass validation now enforce at most one of `forEach`, `forEachOrNull`, or `repeat`. |
| QA-002 | SPEC_VIOLATION | RESOLVED | SQL generation now routes full leading built-in-variable FHIRPath tails to the correct current/root JSON input, and rejects mixed root/current built-ins inside iterators before silent misrouting. |

## Files Changed

- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/viewdef/AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/GLOBAL_KNOWLEDGE.md`
- `fhir4ds-private/docs/prompts/.ai_loop/ARCHIVE_LOG.md`

## Fix Notes

`QA-001` was fixed at both JSON parser and `validate_view_definition()` boundaries so public constructors do not defer the logical-model constraint to SQL generation.

`QA-002` was fixed by broadening built-in variable routing from simple dot-navigation only to full leading-variable FHIRPath tails. Expressions that mix root and current built-ins under an iterator now raise `ValidationError`, because the current DuckDB UDF surface accepts only one JSON evaluation input.

## Validation

- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py::TestSelectParsing::test_parse_rejects_mutually_exclusive_iteration_fields fhir4ds/viewdef/tests/unit/test_parser.py::TestValidation::test_validate_rejects_repeat_with_foreach_variants -q` -> `5 passed`
- `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_foreach_complex_builtin_variable_paths_match_native_and_fallback fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_foreach_mixed_builtin_variable_paths_fail_before_silent_misrouting -q` -> `2 passed`
- `python3 -m pytest fhir4ds/viewdef/tests -q` -> `838 passed`
- `python3 conformance/scripts/run_viewdef.py` -> `134/134`
- `python3 conformance/scripts/run_all.py` -> overall `2822/2822`
- `python3 -m pytest fhir4ds/ -x --tb=short` -> `7376 passed, 5 skipped, 9 warnings`
