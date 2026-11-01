# CQL-02 SKEPTIC Engineer Handoff

## Remediation

- `fhir4ds/cql/translator/expressions/_core.py`
  - Added JSON-shaped CQL Code and Concept literal builders.
  - Updated code selectors, named code refs, concept refs, and codesystem-qualified code refs to emit clinical JSON values instead of legacy `system|code` strings.
- `fhir4ds/cql/translator/expressions/_query.py`
  - Added static clinical type detection for `Code`, `Concept`, `ValueSet`, `CodeSystem`, and `Vocabulary`.
  - Routed clinical `is` checks through that static type layer before generic FHIR `resourceType` extraction.
- `fhir4ds/cql/translator/expressions/_operators.py`
  - Added clinical `as` assertion handling: exact clinical matches pass, `Vocabulary` accepts `ValueSet` and `CodeSystem`, mismatches return NULL.
  - Limited static clinical `as` short-circuiting to source expressions with known clinical types so dynamic FHIR expressions such as `O.value as Concept` still use runtime matching.
  - Kept legacy `system|code` support in code equivalence resolution for compatibility while new translator output uses JSON Code values.
- `fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`
  - Added native-vs-forced-fallback clinical type execution parity.
  - Preserved parser and value-set DuckDB surface coverage with the updated JSON Code literal expectation.

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds pytest -q fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py` -> 5 passed.
- `PYTHONPATH=/mnt/d/fhir4ds pytest -q fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py` -> 11 passed.
- `PYTHONPATH=/mnt/d/fhir4ds pytest -q fhir4ds/cql/tests/unit/test_parser.py fhir4ds/cql/tests/unit/test_c2_library_code_constants.py fhir4ds/cql/tests/unit/test_gap_remediation.py::TestGap12Equivalence` -> 92 passed.
- `PYTHONPATH=/mnt/d/fhir4ds pytest -q fhir4ds/cql/duckdb/tests/test_quantity_udf.py fhir4ds/cql/duckdb/tests/test_valueset_udf.py` -> 87 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_cql.py` -> 1706/1706 passed.
- Targeted DQM rerun for CMS646, CMS1056, CMS826, and CMS122 -> 4/4 measures at 100%.
- `PYTHONPATH=/mnt/d/fhir4ds pytest -q fhir4ds/cql/tests fhir4ds/cql/duckdb/tests` -> 4894 passed, 5 skipped.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes

- No native C++ CQL source change was required; the native path was still tested through public DuckDB registration.
- `spec_schedule.json` was not changed and no archive movement was performed.
