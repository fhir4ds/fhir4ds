# Engineer Handoff - SOF-VD-04 HISTORIAN

## Triage

| Issue | Severity | Category | Result |
| --- | --- | --- | --- |
| QA-001 | MEDIUM | SPEC_VIOLATION | RESOLVED |
| QA-002 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fixes

- `QA-001`: `column.type` now normalizes full StructureDefinition URI
  fragments such as
  `http://hl7.org/fhir/StructureDefinition/Observation#Observation.referenceRange`
  and treats element-ID declarations such as `Observation.referenceRange` as
  JSON-valued non-primitive output. Runtime cardinality guards remain, but the
  unreliable direct `type().name` equality check is skipped for element IDs.
- `QA-002`: `$this` column generation now applies JSON-shape guards before
  returning the value. Untyped or primitive-declared `$this` columns error on
  JSON object/array values; complex and element-ID `$this` declarations reject
  non-complex values.

## Files Changed

- `fhir4ds/viewdef/types.py`
- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/unit/test_columns.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd_04_historian_probe.py`

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/sof_vd_04_historian_probe.py`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_columns.py::TestTypeMapping::test_element_id_type_mapping fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_element_id_type_uri_executes_native_and_fallback fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_this_nonprimitive_type_errors_native_and_fallback -q --tb=short`
  - `3 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests -q --tb=short`
  - `819 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_viewdef.py`
  - `134/134 tests passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py`
  - ViewDefinition `134/134`
  - FHIRPath `935/935`
  - CQL `1706/1706`
  - DQM `47/47`
  - Overall `2822/2822`
