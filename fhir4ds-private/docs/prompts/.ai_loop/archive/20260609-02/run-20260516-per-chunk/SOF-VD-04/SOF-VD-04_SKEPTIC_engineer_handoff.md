# Engineer Handoff: SOF-VD-04 SKEPTIC

## Fixed Issues

- `SOF-VD-04-QA-001`: `column.collection` now defaults to scalar behavior with
  runtime enforcement. Generated SQL raises when a `collection=false` column
  produces multiple FHIRPath values instead of silently projecting the first.
- `SOF-VD-04-QA-002`: `column.type` now normalizes full FHIR StructureDefinition
  URIs to supported type behavior, routes supported complex datatypes through
  JSON output, fails fast for unsupported declarations, and reports missing
  type for simple non-primitive resource paths.
- `SOF-VD-04-QA-003`: Primitive type mismatches on simple top-level resource
  paths now raise execution errors instead of collapsing to NULL. The runtime
  type guard is deliberately limited to simple root-resource navigation to
  preserve valid literal/function/nested `forEach` expressions.
- `SOF-VD-04-QA-004`: Added `ColumnTag` parsing and preservation. `tag`/`tags`
  entries must be arrays of objects with non-empty string `name` and `value`.
  Tags remain metadata and do not alter generated SQL semantics.

## Recovery Note

The first remediation attempt applied `type().name` validation to every column
expression and regressed official ViewDefinition fixtures involving literals,
functions, and nested unrolled element contexts. The required deep-research
report was appended to
`fhir4ds-private/docs/prompts/.ai_loop/state/deep_research_findings.md`, and
the final fix narrows type checks while retaining broad cardinality checks.

## Validation

- `python3 -m py_compile fhir4ds/viewdef/types.py fhir4ds/viewdef/parser.py fhir4ds/viewdef/generator.py`
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py fhir4ds/viewdef/tests/unit/test_columns.py fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_collection_true_output_matches_native_and_fallback fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_non_collection_multivalue_errors_native_and_fallback fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_type_uri_and_mismatch_reporting_native_and_fallback -q --tb=short` -> 192 passed
- `python3 -m pytest fhir4ds/viewdef/tests -q --tb=short` -> 816 passed
- `python3 conformance/scripts/run_viewdef.py` -> 134/134 passed
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_04_skeptic_probe.py` -> target behaviors confirmed across native and forced Python fallback paths where applicable

## Files Touched

- `fhir4ds/viewdef/types.py`
- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/tests/unit/test_generator.py`
- `fhir4ds/viewdef/tests/unit/test_columns.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/viewdef/AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`
- `fhir4ds-private/docs/prompts/.ai_loop/qa_handoff.md`
- `fhir4ds-private/docs/prompts/.ai_loop/state/deep_research_findings.md`
