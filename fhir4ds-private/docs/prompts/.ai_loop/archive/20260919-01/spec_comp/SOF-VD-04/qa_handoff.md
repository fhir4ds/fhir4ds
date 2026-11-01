# QA Handoff — SOF-VD-04 (HISTORIAN), iteration 1

Chunk: ViewDefinition.select.column.{collection,type,tag}. Spec anchor: canonical
SQL-on-FHIR v2 2.0.0 StructureDefinition-ViewDefinition (fetched from
HL7/sql-on-fhir `releases` branch to ig/2.0.0/StructureDefinition-ViewDefinition.json;
saved at /mnt/d/fhir4ds/.temp/qa/sof_vd04_historian/sd-viewdefinition-v2.json),
including the sql-name invariant and the collection/type/tag element definitions.

## Spec sentences verified (normative)
- collection: "Defaults to false if unset. ... SHALL report an error if multiple values
  are produced when that is not the case" — conformant (native + Python fallback, PARITY):
  multi-valued backbone + collection=false errors on both engines; singleton/absent OK.
- type: URI normalization (relative, full SD URI, element-ID fragment form), "must be
  provided if ... non-primitive", "should report an error if the returned type does not
  match" — conformant incl. prior-launch fixes re-verified (cross-resource element-ID
  rejected at generation with actionable message).
- sql-name on column.name (^[[A-Za-z]][[A-Za-z0-9_]]*$): parse-time rejection of `_bad`,
  `1bad`, `bad-name`, `bad name`; `good_name1` accepted. Conformant.
- "column names in the output must not have any duplicates": duplicates within a select
  tree rejected at parse. Conformant.
- tag 0..*, tag.name 1..1, tag.value 1..1: non-string/null/empty name/value rejected;
  3-tag round-trip preserved; tags never alter base semantics (ansi/type=VARCHAR on a
  string column leaves output unchanged).

## New probes beyond the SKEPTIC pass (all PARITY native vs fallback where executed)
- collection=true with complex element types (HumanName, full-URI and relative; element-ID
  backbones Observation.referenceRange) → LIST of JSON, correct.
- collection=true full-URI primitive (…/StructureDefinition/string) → typed list. OK.
- Declared decimal vs integer-valued path → 2.0 (numeric widening accepted; JSON has no
  integer/decimal distinction — acceptable). Declared integer control returns 2.
- Declared string vs code-valued element (gender) → accepted (string-supertype). OK.
- Complex value under primitive declaration (name declared string, collection both
  settings) → runtime type-violation error on both engines. Correct.
- Mixed primitive union collection (given | family) → single string list. OK.
- type URI edges: trailing space rejected; 'http://…/StructureDefinition/' (empty tail)
  rejected; fragment on primitive URI rejected with unsupported-type list.

## Issues
- QA-001 (LOW, OPEN): absolute column.type URI with uppercase scheme
  ('HTTP://hl7.org/fhir/StructureDefinition/string') is misclassified as an element-ID
  declaration and rejected with a misleading cross-resource element-ID error message
  instead of an unsupported/absolute-URI-type diagnostic. Rejection is defensible
  (canonical URLs are case-sensitive) but the diagnostic is wrong.
- QA-002 (LOW, INTENDED): same-resource element-ID misdeclaration (e.g. type
  'Patient.contact' on a path returning HumanName) is never reported. Spec verb is
  "should" (non-SHALL) and backbones are not runtime-typeable; documented portable-guard
  doctrine from the SKEPTIC launch (see spec_comp/SOF-VD-04/). Logged for the record.

Zero CRITICAL/HIGH/MEDIUM issues.

Probes: /mnt/d/fhir4ds/.temp/qa/sof_vd04_historian/probe.py (+ inline reruns in this log).
