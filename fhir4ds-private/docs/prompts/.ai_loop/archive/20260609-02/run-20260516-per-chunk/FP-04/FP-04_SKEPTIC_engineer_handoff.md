# Engineer Handoff - FP-04 SKEPTIC

Resolved issues:
- `QA-001`: `ofType(Resource)` / `ofType(DomainResource)` now include Patient and Observation resources in Python core, forced Python DuckDB fallback, and native C++ DuckDB paths. The fix is intentionally narrowed so official R4 primitive behavior remains intact (`Patient.gender.ofType(string)` stays empty for FHIR `code`).
- `QA-002`: Python filtering/projection macros now save and restore `$index`; `repeat()` binds `$index` while processing queued items; undefined `$index`/`$total` evaluate to empty, matching public wrapper/native behavior.

Files changed:
- `fhir4ds/fhirpath/engine/invocations/filtering.py`
- `fhir4ds/fhirpath/engine/evaluators/__init__.py`
- `fhir4ds/fhirpath/engine/nodes.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py`
- `extensions/fhirpath/AGENTS.md`

Validation:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` -> 3 passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit fhir4ds/fhirpath/duckdb/tests/integration -q` -> 245 passed.
- `python3 conformance/scripts/run_fhirpath_r4.py` -> FHIRPath R4 935/935 passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath` -> all tests passed, 114 assertions.

Notes:
- The bundled native extension was rebuilt from `extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension` and copied into `fhir4ds/fhirpath/duckdb/extensions/`.
- No new issues were discovered during remediation.
