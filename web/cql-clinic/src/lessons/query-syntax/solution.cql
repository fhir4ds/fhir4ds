library QuerySyntax version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

define "Final Obs Count":
  Count([Observation] O where O.status = 'final')
define "Max Value":
  Max([Observation] O where O.valueQuantity.value is not null return O.valueQuantity.value)
define "Avg Value":
  Avg([Observation] O return O.valueQuantity.value)
define "Earliest Obs Id":
  First([Observation] O sort by (O.effective as FHIR.dateTime) return O.id)
define "Singleton Value":
  singleton from ([Observation] O where O.id = 'obs-2' return O.valueQuantity.value)
define "First Tuple":
  First([Observation] O return Tuple { id: O.id, status: O.status })
define "Distinct Statuses":
  Count(distinct ([Observation] O return O.status))
define "BP With Let":
  Count([Observation] O let isBP: O.code.coding.code contains '8480-6' where isBP)
define "High Final Count":
  Count([Observation] O where O.status = 'final' and O.valueQuantity.value > 100)
define "Union Count":
  Count([Observation] union [Condition])
