# Engineer Handoff — SOF-SQ-01, HISTORIAN launch (iteration 1)

All 5 QA issues (QA-001..QA-005) RESOLVED with focused regression tests.

## Files changed

- fhir4ds/sqlquery/types.py
  - Added LIBRARY_TYPES_CODESYSTEM_CANONICALS and matches_profile_canonical()
    (moved from parser; parser now imports it).
  - SQLContent/SQLRelatedArtifact/SQLParameter gained verbatim extra_fields
    bags (repr/compare=False).
  - _SQLLibraryBase gained meta (verbatim source meta) and type_concept
    (verbatim source type) fields.
  - to_dict rewritten: preserves source meta/type verbatim; appends the
    profile canonical to meta.profile only when no recognized declaration is
    present (never rewrites an official canonical); merges per-entry
    extra_fields before modeled keys (contentType/data, type/label/resource,
    name/type/use); extra_fields merged last but now contains every
    unmodeled top-level key (description, publisher, extension, ...).
- fhir4ds/sqlquery/parser.py
  - _MODELED_LIBRARY_KEYS replaces _KNOWN_LIBRARY_KEYS (only keys to_dict
    re-emits from dataclass fields are excluded from the verbatim bag).
  - _require_type_coding: rejects a coding whose system is present but not
    LibraryTypesCodes (absent system tolerated).
  - parse_library: enforces Library.status 1..1; captures meta/type_concept.
  - _parse_parameter: validates parameter.type against the
    fhir_type_to_duckdb registry (data-driven authority) — non-FHIR-primitive
    types raise SQLQueryParseError at parse time.
  - _parse_content/_parse_related_artifact/_parse_parameter capture per-entry
    extra_fields.
- Tests: fhir4ds/sqlquery/tests/test_sof_sq01_compliance.py (+15 tests:
  TestRoundtripFullFidelity, TestStatusRequired, TestParameterTypeIsFhirPrimitive,
  TestTypeCodingSystem); fixtures gained status="active"; integration test
  test_unknown_fhir_type_rejected moved to the parse-time typed rejection
  path (SQLQueryParseError).

## Validation

- fhir4ds/sqlquery/tests: 70/70 passed (was 55).
- Master gate: conformance/scripts/run_all.py OVERALL 2832/2832 (baseline
  held). Binary md5s unchanged, repo == site-packages:
  cql.duckdb_extension c5b22d58310c1eb7bafa17ce7877f989;
  fhirpath.duckdb_extension 57d0634b6ee6eddee9fc06a1355bef5a (no native
  changes this launch).

No workarounds; all fixes target root causes in the data model. Spec
citations in evolution.json issues.
