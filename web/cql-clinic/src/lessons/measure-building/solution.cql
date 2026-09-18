library MeasureBuilding version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// A real eCQM shape: Initial Population -> Denominator (with exclusion)
// -> Numerator. Population membership is Boolean-per-patient.
//
// The mini-measure: "Diabetes patients with a recent HbA1c test".
//   Initial Population: diabetic patients aged 18-75 at 2024-01-01
//   Denominator: in IP AND had an office visit in the measurement period
//   Denominator Exclusion: patients in hospice during the period
//   Numerator: denominator patients with HbA1c (LOINC 4548-4) in 2024

define "Measurement Period":
  Interval[@2024-01-01, @2024-12-31]

define "Has Diabetes":
  exists([Condition] C where exists(C.code.coding cod where cod.code = '44054006' and cod.system = 'http://snomed.info/sct'))

define "Age At Start": AgeInYearsAt(start of "Measurement Period")

define "Initial Population":
  "Has Diabetes" and "Age At Start" between 18 and 75

define "Had Office Visit":
  exists([Encounter] E where E.class.code = 'AMB' and E.period during "Measurement Period")

define "In Hospice":
  exists([Encounter] E where E.class.code = 'HH' and E.period during "Measurement Period")

define "Denominator":
  "Initial Population" and "Had Office Visit"

define "Denominator Exclusion":
  "Denominator" and "In Hospice"

define "Has Recent A1c":
  exists([Observation] O where exists(O.code.coding cod where cod.code = '4548-4' and cod.system = 'http://loinc.org') and (O.effective as FHIR.dateTime) during "Measurement Period")

define "Numerator":
  "Denominator" and not "Denominator Exclusion" and "Has Recent A1c"
