library QuerySyntax version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// Alice has 3 observations (2 final, 1 preliminary) and 1 condition.
// Bob has 1 final observation. Every define below works per-patient.

define "Final Obs Count":
  Count([Observation] O where O.status = 'final')
// TODO: "Max Value" must return the highest valueQuantity.value across
//   observations (guard against null with 'is not null' in the where)
// TODO: "Avg Value" must average valueQuantity.value across observations
// TODO: "Earliest Obs Id" must return the id of the chronologically first
//   observation (sort by the effective date — cast the choice type)
// TODO: "Singleton Value" must use singleton from to extract obs-2's
//   valueQuantity.value (a query that returns exactly one row)
// TODO: "First Tuple" must return Tuple { id: ..., status: ... } for the
//   first observation
// TODO: "Distinct Statuses" must count unique observation statuses
// TODO: "BP With Let" must use a let clause: bind isBP to whether the
//   observation's LOINC code is 8480-6, filter with it, and count
// TODO: "High Final Count" must count final observations with
//   valueQuantity.value > 100
// TODO: "Union Count" must count observations unioned with conditions
