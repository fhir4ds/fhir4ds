library Terminology version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// Three patients: Alice has SNOMED + ICD + SNOMED conditions,
// Bob has an ICD-coded condition, Cara has none.
// Declare your vocabulary first, then match codings carefully.

codesystem "SNOMED": 'http://snomed.info/sct'
codesystem "ICD10CM": 'http://hl7.org/fhir/sid/icd-10-cm'

code "Diabetes SNOMED": '44054006' from "SNOMED" display 'Diabetes mellitus'
code "T2DM ICD": 'E11.9' from "ICD10CM" display 'Type 2 diabetes'

// TODO: "Has SNOMED Diabetes" must be true when any Condition has a coding
//   matching BOTH the code and system of "Diabetes SNOMED"
// TODO: "Has ICD T2DM" must match "T2DM ICD" the same way
// TODO: "SNOMED Condition Count" must count conditions with any SNOMED coding
//   (compare cod.system to the SNOMED URL directly)
// TODO: "ICD Condition Count" must count conditions with any ICD-10-CM coding
// TODO: "First SNOMED Display" must return the display of the first coding
//   of the first SNOMED-coded condition
// TODO: "Declared Code Display" must return the display of "Diabetes SNOMED"
// TODO: "Diabetes By Any System" must be true when any coding code equals
//   the diabetes code, ignoring system
// TODO: "Codings Per Condition" must return how many codings Alice's
//   conditions have in total (use a query with return)
// TODO: "Has Hypertension" must match SNOMED 38341003 — and teach the lesson:
//   Bob's hypertension is ICD-coded, so this returns false everywhere!
