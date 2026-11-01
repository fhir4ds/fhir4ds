# QA Handoff — SOF-VD-11 SKEPTIC, iteration 1 (2026-08-23)

## Probed (all behavioral, native extension active unless noted)
- Fresh spec-suite run: 465/465 pytest items (144-test ViewDef suite) — baseline holds.
- Upstream drift check: FHIR/sql-on-fhir.js tests/ downloaded fresh; 22/22 spec_tests
  files hash-identical to local snapshot (md5). NO DRIFT since 2026-08-11.
- All 5 published IG 2.0.0 Binary examples (PatientAddresses,
  PatientAndContactAddressUnion, PatientDemographics, ShareablePatientDemographics,
  UsCoreBloodPressures) fetched from sql-on-fhir.org/ig/2.0.0, decoded, parsed,
  generated, executed end-to-end against representative Patient/Observation data.
  All OK; output shapes match the documented pages.
- Documented expected table reproduced EXACTLY: PatientDemographics page's
  id/gender/given_name/family_name table (getResourceKey() returns "Patient/1"
  form; names/values identical).
- Type coercion: integer→INTEGER, integer64→BIGINT, decimal→DOUBLE,
  boolean→BOOLEAN, date/dateTime/time→VARCHAR (fixture-pinned string semantics,
  spec_tests assert string equality — NOT A BUG), complex types→VARCHAR JSON,
  collection=true→VARCHAR[] / typed arrays. Runtime collection=false/type guard
  fires correctly (decimal 95.5 into type:integer rejected with typed error).
- Engine parity: native (allow_unsigned_extensions at connect) vs Python fallback
  — identical column types AND rows on all example views.
- where-filtered Observation views work (top-level where + status filter).
- Forward-drift OBSERVATION (report-only, no fix): FHIR/sql-on-fhir-v2 repo HEAD
  example VDs now use resourceType "ViewDefinition" + resourceDefinition
  "...ViewDefinition|3.0.0-ballot" (3.0.0-ballot era, commits 2026-08-06/07) and
  are REJECTED by the 2.0.0-canonical parser requirement. Not drift of the
  pinned 2.0.0 surface; flag for the release checklist re-sync decision.

## Finding
- QA-001 MEDIUM OPEN: dead unsigned-retry branch in
  fhir4ds/fhirpath/duckdb/extension.py (`SET allow_unsigned_extensions = true`
  after connect can never succeed on a running DB) → register_fhirpath silently
  downgrades to Python UDFs; misleading code path + INFO-only visibility.
  Parity confirmed, so correctness is unaffected.

Probes: .temp/qa/sof_vd11_skeptic_2026_08_23/{probe_ig_examples,probe_engine_paths,probe_ig20_examples}.py
