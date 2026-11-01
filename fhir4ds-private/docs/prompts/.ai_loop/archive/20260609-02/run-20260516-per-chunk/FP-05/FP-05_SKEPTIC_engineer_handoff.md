# Engineer Handoff - FP-05

Resolved issues:
- QA-001: Enforced Integer-only arguments for `[index]`, `skip(num)`, and `take(num)` in Python core and native C++ evaluator. Strings, booleans, decimals, and JSON reals now produce semantic errors that public DuckDB wrappers convert to empty/NULL.
- QA-002: Replaced Python core `intersect()` JSON/repr key matching with FHIRPath `=` equality, and aligned direct `FHIRPathCollection` set helpers with the same equality semantics.

Files changed:
- `fhir4ds/fhirpath/engine/__init__.py`
- `fhir4ds/fhirpath/engine/evaluators/__init__.py`
- `fhir4ds/fhirpath/engine/invocations/subsetting.py`
- `fhir4ds/fhirpath/engine/invocations/combining.py`
- `fhir4ds/fhirpath/duckdb/collection.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py`
- `AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

Validation:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py -q --tb=short` -> 3 passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py -q --tb=short` -> 275 passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath` -> 114 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration -q --tb=short` -> 79 passed.
- `python3 conformance/scripts/run_fhirpath_r4.py` -> 935/935 passed in `conformance/reports/fhirpath_report.json`.

New issues discovered: none.
