library References version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// FHIR resources point at each other with Reference elements. A
// MedicationRequest does not embed the drug — it carries a reference
// string like 'Medication/med-ator'. Three patients:
//   Ana:  active atorvastatin request + COMPLETED ibuprofen request
//   Bob:  active ibuprofen request
//   Cara: active request pointing at a medication that doesn't exist
//
// RxNorm ingredient codes: atorvastatin 268490, ibuprofen 5640.

// TODO: "Active Request Count" must count only status = 'active' requests

define "All Request Count":
  Count([MedicationRequest])

// TODO: "Reference String" must return the reference string of the active
//   request — cast the medication choice to FHIR.Reference, then .reference
// TODO: "Referenced Med Id" must extract the logical id (final path
//   segment) using Split and Last
// TODO: "Uses Medication Reference" must be true when the reference string
//   starts with 'Medication/' (StartsWith)
// TODO: "Resolved Med Code" must follow the reference with resolve() and
//   return the RxNorm coding's code — or null when nothing resolves
// TODO: "On Ibuprofen" must be true when an ACTIVE request resolves to a
//   Medication coded 5640 in RxNorm
// TODO: "Dangling Reference" must flag patients whose active request
//   resolves to no code (resolve of a missing target is null)
