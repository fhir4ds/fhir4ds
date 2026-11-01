# Engineer Handoff: SOF-VD-07 EXPLORER

Phase: FIX
Issue count: 1

## Resolved

- `QA-001` HIGH `RESOLVED`: forced Python fallback `fhirpath_repeat` silently returned an empty result for deeply nested raw JSON after hitting parser/evaluator/serializer recursion limits, while the native C++ extension returned the expected repeated nodes.

## Root Cause

The fallback repeat path used `orjson.loads`, recursive traversal, default Python recursion limits during FHIRPath evaluation, and recursion-limited JSON serialization for each repeated child node. For valid finite raw JSON with deeply nested `item` structures, one of those depth limits raised internally and the public UDF converted the error to `[]`, dropping all `select.repeat` rows.

## Fix

- Added a depth scanner and a depth-aware parse fallback in `fhir4ds/fhirpath/duckdb/udf.py`.
- Kept a temporary depth-derived recursion budget around fallback `fhirpath_repeat` evaluation under a recursion-limit lock.
- Replaced fallback repeat recursive DFS with explicit stack frames preserving the prior preorder/path traversal behavior.
- Added iterative JSON serialization for repeated child node output when the fast serializers hit recursion ceilings.
- Added a raw JSON ViewDefinition regression that compares forced Python fallback with native C++ at nested `QuestionnaireResponse.item` depth 800.

## Files Changed

- `fhir4ds/fhirpath/duckdb/udf.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/fhirpath/AGENTS.md`
- `fhir4ds/viewdef/AGENTS.md`
- `.ai_loop/evolution.json`
- `.ai_loop/qa_handoff.md`

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m py_compile fhir4ds/fhirpath/duckdb/udf.py`
- Focused native/fallback raw JSON probe at depths 300, 800, 1100, and 1500: native and fallback counts/first/last matched.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py::TestRepeat::test_repeat_deep_raw_json_matches_native_and_fallback -q` -> `1 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py fhir4ds/viewdef/tests/integration/test_duckdb.py::TestRepeat -q` -> `11 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py -q` -> `181 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef -q` -> `848 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> overall `2822/2822`, all suites `100.0%`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/ -x --tb=short | tail -n 50` -> `7387 passed, 5 skipped, 9 warnings`

## Notes for Architect

Review the recursion-budget scope and iterative serializer. The intended boundary is narrow: only the Python fallback repeat path needs to support raw JSON nesting beyond the normal parser/serializer limits so it matches the already-working C++/yyjson surface.
