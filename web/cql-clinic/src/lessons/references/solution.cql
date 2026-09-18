library References version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// FHIR resources point at each other with Reference elements: a
// MedicationRequest carries medication: { reference: 'Medication/med-1' } —
// a type prefix plus the target's logical id. Three patients:
//   Ana:  an active request for atorvastatin + a COMPLETED ibuprofen
//         request (status filtering matters)
//   Bob:  an active request for ibuprofen
//   Cara: an active request whose medication target does not exist —
//         a dangling reference
//
// RxNorm ingredient codes: atorvastatin 268490, ibuprofen 5640.

define "Active Request Count":
  Count([MedicationRequest] R where R.status = 'active')

define "All Request Count":
  Count([MedicationRequest])

define "Reference String":
  First([MedicationRequest] R where R.status = 'active' return (R.medication as FHIR.Reference).reference)

define "Referenced Med Id":
  First([MedicationRequest] R where R.status = 'active' return Last(Split((R.medication as FHIR.Reference).reference, '/')))

define "Uses Medication Reference":
  exists([MedicationRequest] R where R.status = 'active' and StartsWith((R.medication as FHIR.Reference).reference, 'Medication/'))

define "Resolved Med Code":
  First([MedicationRequest] R where R.status = 'active'
    return First(resolve(R.medication as FHIR.Reference).code.coding C where C.system = 'http://www.nlm.nih.gov/research/umls/rxnorm').code)

define "On Ibuprofen":
  exists([MedicationRequest] R where R.status = 'active'
    and exists(resolve(R.medication as FHIR.Reference).code.coding C where C.code = '5640' and C.system = 'http://www.nlm.nih.gov/research/umls/rxnorm'))

define "Dangling Reference":
  "Active Request Count" > 0 and "Resolved Med Code" is null
