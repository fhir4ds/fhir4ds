# Engineer Handoff - FP-04 EXPLORER

Issue remediated:
- QA-001 MEDIUM, `fhir4ds.fhirpath.duckdb.functions.filter` helper API §5.2 compliance.

Fix summary:
- `where()` now accepts only empty or singleton Boolean criteria. Non-Boolean and multi-item criteria raise `FHIRPathError`.
- `select()` now propagates evaluator failures as `FHIRPathError` instead of silently dropping failed projections.
- `repeat()` now returns projection results only, does not pre-seed output with input items, and de-duplicates both accumulated and same-batch projection results via FHIRPath `=` equality.
- `of_type()` now resolves concrete resources and supertypes such as `DomainResource` and `Resource` through FHIR model `type2Parent` metadata.
- Added regression tests for strict `where`, projection-only `repeat`, duplicate projection de-duplication, and resource subtype `of_type`.

Validation:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` -> 110 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration -q` -> 77 passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q` -> 8 passed.
- Fresh-process native C++ DuckDB and forced Python fallback checks matched for FP-04 `repeat`, strict `where` wrapper behavior, and `ofType(Resource/DomainResource/Patient)`.
- `python3 conformance/scripts/run_fhirpath_r4.py` -> report shows 935/935 passed.

New issues discovered:
- None.
