# QA Handoff — SOF-VD-12 HISTORIAN (2nd launch, iteration 1, 2026-08-23)

## Probed (workspace .temp/qa/sof_vd12_historian2/, 9/9 PASS)
SKEPTIC fix re-verified plus NEW divergence hunt:
- Fetched ACTUAL Shareable/Tabular profile SDs from upstream HL7/sql-on-fhir HEAD
  AND the canonical ig/2.0.0 build (local /tmp/sof2/ig/2.0.0). Enumerated EVERY
  differential element/constraint. Result: the implemented rule set is COMPLETE.
  Shareable = url min1, name min1, fhirVersion min1, select.column.type min1.
  Tabular = INV no-collections + INV primitives-only with the identical 18-type
  code list (byte-for-byte match vs TABULAR_PRIMITIVE_TYPE_NAMES). The 2.0.0 and
  HEAD differentials are identical to each other and to the implementation.
- Profile rules at NESTED levels: violations in select.select AND select.unionAll
  columns are correctly rejected for both profiles (via _iter_select_columns).
- Versioned canonicals (Shareable|1.2.3): enforcement triggers (version stripped
  for matching); meta.profile retained verbatim in to_dict.
- Foreign unknown-profile canonicals: ignored for enforcement AND retained
  verbatim — consistent with official validator (sof-js validate.js does not
  inspect meta.profile at all).
- Full-URI Column.type under Tabular ("http://hl7.org/fhir/StructureDefinition/code"):
  accepted and normalized to "code" — consistent with 2.0.0 column.type being a
  `uri` and the long-standing ColumnType.normalize_name doctrine. NOT A BUG.
- Plain VD without status: ACCEPTED. Pinned NOT A BUG: canonical base SD snapshot
  says status 1..1, but the official runtime validator (FHIR/sql-on-fhir.js
  sof-js/src/validate.js) requires only ['resource','select'] — fixtures/validator
  outrank prose. Profiled VDs missing status ARE rejected (stricter than official
  validator, documented stance).
- Official 2.0.0 example Binary-ShareablePatientDemographics: parse ->
  to_dict round-trip BYTE-IDENTICAL; SQL generated; DuckDB execution correct
  ([('Patient/pat1','male','John Q','Doe')]) including the forEach
  name.where(use='official').first() path (0 rows without official use = correct).
- mapping/publisher round-trip retained verbatim (re-confirmed).
- resourceType:"ViewDefinition" + resourceDefinition (upstream HEAD 3.0.0-ballot
  form) rejected — pre-adjudicated FORWARD DRIFT (SOF-VD-11 SKEPTIC), not re-logged.

## Findings
Zero new issues. SKEPTIC's QA-001 fix verified spec-correct and regression-free.

## Gates
viewdef pytest 1232 passed; ViewDef conformance 144/144; master 2832/2832;
fhirpath ext md5 57d0634b..., cql ext md5 c5b22d58... (repo == site-packages).
