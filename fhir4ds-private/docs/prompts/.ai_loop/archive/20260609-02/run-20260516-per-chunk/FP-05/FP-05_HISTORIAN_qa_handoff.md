# QA Handoff - FP-05 HISTORIAN

Scope: FHIRPath §5.3 Subsetting and §5.4 Combining.

Spec source checked: HL7 FHIRPath Normative Release §3.1 collections and §5.3/§5.4 functions at https://hl7.org/fhirpath/N1/.

Hypotheses tested:
- Integer-only argument enforcement for `[index]`, `skip(num)`, and `take(num)` across native C++ and forced Python fallback.
- Boundary semantics for empty, negative, zero, out-of-range, and multi-item index/count arguments.
- `single()` strict core error behavior versus DuckDB row-resilient empty/NULL behavior.
- Duplicate/order rules for `tail()`, `skip()`, `take()`, `exclude()`, and `combine()`.
- FHIRPath equality reuse for `intersect()` and `union()` with compatible quantities and structurally equal JSON objects whose member order differs.

Result: No new FP-05 bugs found. Native C++ extension and forced Python fallback matched expected behavior for all probed public DuckDB UDF surfaces. Direct Python core preserved strict errors for multi-item `single()` and invalid Integer arguments.

Validation:
- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/fp05_historian_probe.py` passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py -q` passed: 11/11.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/tests/unit/test_new_functions.py -q` passed: 69/69.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_fhirpath_r4.py` produced `conformance/reports/fhirpath_report.json`; parsed result: 935/935 passed.
