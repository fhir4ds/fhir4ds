# Engineer Handoff - FP-14 SKEPTIC

Resolved all open FP-14 comparison issues against FHIRPath N1 Section 6.2.

Fixes:
- `QA-001`: Boolean operands no longer produce ordered comparison results. Native C++ raises a typed spec error for same-type Boolean comparisons; Python fallback raises `FHIRPathError`. Public DuckDB result UDFs remain row-resilient and return empty/NULL.
- `QA-002`: Multi-item comparison operands now raise internal singleton errors in both native C++ and Python fallback. Public result UDFs still return empty/NULL, while literal multi-item cases such as `(1 | 2) < 3` and `1 < (2 | 3)` now make `fhirpath_is_valid()` false.
- `QA-003`: Calendar duration keywords compared with UCUM duration codes above seconds now return empty for ordering comparisons. Seconds and milliseconds remain comparable, preserving the Section 6.2 exception.

Implementation:
- Python: tightened `fhir4ds/fhirpath/engine/invocations/equality.py::_compare` and added mixed calendar/UCUM duration comparison guards in `FP_Quantity.compare`.
- Native C++: tightened `extensions/fhirpath/src/fhirpath/evaluator.cpp` comparison handling for Boolean operands, multi-item operands, and mixed calendar/UCUM duration quantities.
- Tests: extended comparison parity coverage and native sqllogictest regressions.
- Rebuilt and copied the bundled native extension to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Validation:
- Fresh QA probe after fix: 41 cases, 0 mismatches, 0 expectation failures.
- Focused pytest: `test_comparison_parity.py` 8 passed.
- Native FHIRPath sqllogictest: 578 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No new issues were discovered.
