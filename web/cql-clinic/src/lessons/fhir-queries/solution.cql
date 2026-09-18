library FHIRQueries version '1.0.0'
using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

define "Full Name":
  Patient.name.first().given.first() + ' ' + Patient.name.first().family
define "Is Male": Patient.gender = 'male'
define "Observation Count": Count([Observation])
define "Lab Count":
  Count([Observation] O where exists(O.category C where C.coding.code = 'laboratory'))
define "Systolic BP":
  First([Observation] O where O.code.coding.code = '8480-6' return O.valueQuantity.value)
define "Has Diabetes":
  exists([Condition] C where C.code.coding.code = '44054006')
define "Active Med Count":
  Count([MedicationRequest] MR where MR.status = 'active' and MR.intent = 'order')
