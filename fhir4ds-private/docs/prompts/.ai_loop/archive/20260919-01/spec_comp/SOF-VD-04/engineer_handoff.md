# Engineer Handoff — SOF-VD-04 (HISTORIAN), iteration 1

## QA-001 (LOW) — RESOLVED
- Root cause: `SQLGenerator._is_element_id_type` (fhir4ds/viewdef/generator.py) classified
  any dotted string as element-ID notation. Absolute URIs containing dots (uppercase-scheme
  'HTTP://hl7.org/fhir/StructureDefinition/string', third-party SD URLs, 'urn:oid:1.2.3.4')
  were rejected with the misleading cross-resource element-ID message instead of the
  actionable unsupported-column-type error.
- Fix (spec-grounded: SQL-on-FHIR v2 column.type — element-ID notation is a bare relative
  dotted path; absolute URIs are a distinct form): `_is_element_id_type` now returns True
  only for colon-free dotted strings. Absolute/urn URIs flow to the existing
  "Unsupported ViewDefinition column type … Supported core FHIR types are: …"
  ValidationError. Single classification site; both `_get_udf_for_type`,
  `_is_complex_declared_type`, and `_validate_element_id_column_types` inherit the fix.
- General, not test-specific: covers the class (any scheme incl. urn:), verified with three
  distinct URIs plus same-resource/cross-resource element-ID regressions.

## QA-002 (LOW) — INTENDED (no change)
- Same-resource element-ID misdeclaration (type 'Patient.contact' on a HumanName path) is
  unreported. Spec verb is "should"; backbone elements are not runtime-typeable; matches
  the SKEPTIC-launch portable runtime-guard doctrine. To be added to the NOT A BUG registry.

## Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- New focused test: fhir4ds/viewdef/tests/unit/test_parser.py::
  TestElementIdColumnTypeValidation::test_absolute_uri_type_not_misdiagnosed_as_element_id.
- Related unit files: 421/421. Full ViewDef pytest: 1178/1178 (1177 prior + 1 new).
- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  OVERALL 2832/2832 (baseline holds).
- Binaries untouched (Python-only fix); md5 repo==site-packages:
  cql c5b22d58310c1eb7bafa17ce7877f989, fhirpath 57d0634b6ee6eddee9fc06a1355bef5a.
