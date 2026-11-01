# Engineer Handoff - FP-08 HISTORIAN

Resolved issues:
- `QA-001` MEDIUM: Preserved partial Time precision for `toTime()`/`toString()`. `14:34` now remains `14:34` in native C++ and Python fallback instead of being promoted to `14:34:00`.
- `QA-002` MEDIUM: Fixed forced Python fallback `fhirpath_bool()` type erasure. It now evaluates raw FHIRPath results before boolean conversion, so JSON numeric `1` can still return true while string result `"1"` from `toString()` returns NULL like native C++.

Files changed by this remediation:
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/engine/nodes.py`
- `fhir4ds/fhirpath/duckdb/udf.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `extensions/fhirpath/AGENTS.md`
- `.ai_loop/.temp/qa/fp08_historian_probe.py`

Validation run:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q --tb=short` -> 10 passed.
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp08_historian_probe.py` -> native and forced Python fallback agree.
- `./build/release/test/unittest '*fhirpath*'` -> 150 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests -q --tb=short` -> 1005 passed, 1 pre-existing warning.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit -q --tb=short` -> 169 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Notes:
- Rebuilt native extension with `cmake --build build/release --config Release -j 8` from `extensions/fhirpath` and copied the resulting `fhirpath.duckdb_extension` into the Python package.
- The QA temp script must insert the repo root into `sys.path`; otherwise running a script from `.ai_loop/.temp` can import an installed package instead of this workspace.
