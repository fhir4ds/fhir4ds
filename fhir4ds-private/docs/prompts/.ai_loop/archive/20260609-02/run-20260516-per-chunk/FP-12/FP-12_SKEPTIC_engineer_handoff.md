# Engineer Handoff - FP-12

Resolved issues:
- `QA-001` HIGH: native DuckDB `children()`/`descendants()` now preserve null child nodes. Root cause was split between `fn_children()` null filtering, `EvaluateFhirpath()` dropping null JsonVals during owned materialization, and `fn_count()` excluding JsonVal nulls before materialization. Fix adds an owned native `FPValue::Null` sentinel, counts null child nodes, and serializes `fhirpath_json` nulls as JSON `null`. Python fallback JSON/list output was aligned for null tree-navigation results.
- `QA-002` MEDIUM: Python core `trace(name, projection)` now evaluates/logs projection results while returning the original input unchanged. The trace arity table includes the projection expression, the old raw-parameter slicing is removed, and `$this` is restored after projection evaluation.

Verification:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py fhir4ds/fhirpath/tests/unit/test_new_functions.py::test_trace_projection_logs_projection_and_returns_input -q` -> 3 passed.
- `./build/release/test/unittest "*fhirpath*"` in `extensions/fhirpath` -> 226 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit fhir4ds/fhirpath/duckdb/tests/integration -q` -> 265 passed.
- `python3 conformance/scripts/run_all.py | grep ...` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2822/2822.

Notes:
- Native extension was rebuilt and copied to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
- A deep-research note for `QA-001` was appended because the first native fix attempt exposed a second null drop in UDF materialization.
