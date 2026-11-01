# QA Handoff — SOF-VD-09 EXPLORER

Scope covered: SQL-on-FHIR ViewDefinition root `where` semantics for exact Boolean inclusion, false/empty/null filtering, non-Boolean runtime results, multi-item Boolean results, constants, `where.description` retention, root-resource scope, shared-table resource filtering, and native C++ versus forced Python fallback parity.

Spec basis verified from SQL-on-FHIR v2.0.0: `ViewDefinition.where` is 0..*; every constraint must evaluate true for inclusion; `where.path` is a FHIRPath expression evaluated in the root resource context and may reference constants as `%[name]`; `where.description` is optional string metadata.

Fresh probe: `.temp/qa/sof_vd09_explorer_probe.py`.

Results:
- `multiple_wheres_and_constants`: native and fallback returned `keep` only.
- `false_empty_and_null_exclude`: native and fallback returned no rows.
- `non_boolean_string_true_excludes`: string `"true"` did not include the active row; singleton Boolean true still included the control row.
- `leading_resource_builtin_root_scope`, `embedded_resource_builtin_root_scope`, and `embedded_rootresource_builtin_root_scope`: native and fallback matched expected root-scope rows.
- `multi_item_boolean_collection_excludes`: `[true,false]` did not satisfy root `where`.
- `this_root_context_boolean`: `$this` root context filtered active Patient only.
- `ViewDefinition.from_dict()` retained valid `where.description`.

No issues were found. Existing behavior is spec-compliant for the probed EXPLORER edge cases.

Validation:
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_where.py fhir4ds/viewdef/tests/integration/test_duckdb.py::test_root_where_numeric_results_do_not_satisfy_boolean_true_native_and_fallback fhir4ds/viewdef/tests/integration/test_duckdb.py::test_root_where_literal_one_does_not_satisfy_boolean_true_native_and_fallback -q --tb=short` -> 31 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/test_spec_compliance.py -q --tb=short` -> 435 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
