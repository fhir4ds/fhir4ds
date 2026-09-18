library FHIRQueries version '1.0.0'
using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// TODO: "Full Name" must be this patient's first given name + ' ' + family name
// TODO: "Is Male" must be true when Patient.gender is 'male'
// TODO: "Observation Count" must count all observations for this patient
// TODO: "Lab Count" must count observations whose category coding code is 'laboratory'
// TODO: "Systolic BP" must return the valueQuantity.value of the LOINC 8480-6 observation
// TODO: "Has Diabetes" must be true when any Condition has SNOMED code 44054006
// TODO: "Active Med Count" must count MedicationRequests with status 'active' and intent 'order'
