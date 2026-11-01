# Engineer Handoff — SOF-VD-12 (iteration 1)

## QA-001 (HIGH) — RESOLVED
Root cause: fhir4ds/viewdef/metadata.py recognized the Shareable/Tabular
profiles only under invented canonical URLs
(https://sql-on-fhir.org/ig/StructureDefinition/...). Every published form of
these profile SDs (upstream repo since introduction 2026-08-06; published IG
build.fhir.org/ig/HL7/sql-on-fhir) uses
http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/... — official examples
declaring the profiles therefore got zero enforcement.

Fix (data-driven canonical alias sets, GLOBAL_RULES-compliant):
- metadata.py: added SHAREABLE_VIEWDEFINITION_PROFILE_CANONICALS /
  TABULAR_VIEWDEFINITION_PROFILE_CANONICALS frozensets containing BOTH the
  legacy sql-on-fhir.org/ig spellings (back-compat) and the official
  hl7.org/fhir/uv canonicals.
- types.py validate_supported_view_profiles(): membership test against the
  alias sets.
- Regression: test_parser.py
  test_official_profile_canonicals_trigger_shareable_and_tabular_rules
  (Shareable url/Column.type + Tabular collection/primitive violations under
  the official canonicals, plus conforming round-trip).

Validation: viewdef pytest suite 1232 passed (incl. 144 conformance tests);
master gate run recorded in launch report. Python-only fix; DuckDB extension
binaries untouched (fhirpath 57d0634b..., cql c5b22d58..., repo==site-packages).
