# Engineer Handoff - Fresh 0.0.5 Rerun

Resolved issues:
- QA-001: Preserved core FHIRPath spec behavior while aligning Python DuckDB wrappers with native row-level resilience. `fhirpath_scalar` and wrapper UDFs now return empty/NULL for `FHIRPathError` outside strict mode, while direct core evaluation still raises for execution errors such as multi-item `as(...)`.
- QA-002: Fixed native C++ multi-item equality in `extensions/fhirpath/src/fhirpath/evaluator.cpp`. Multi-item `=`/`!=` now compare ordered collections and return boolean results, including false/true on length mismatch.

Files changed by remediation:
- `fhir4ds/fhirpath/duckdb/udf.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`

Verification:
- Focused reprobe for `(1 | 1) = (1 | 2 | {})`, `arr = 1`, `arr != 1`, and same-length collection equality now matches Python/native.
- Focused pytest: 8 passed for equality parity, collection parity, and conformance regressions.
- Full conformance: 2822/2822.
