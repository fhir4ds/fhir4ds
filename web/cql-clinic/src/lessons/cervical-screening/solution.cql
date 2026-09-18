library CervicalScreening version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// CMS124-shaped cervical cancer screening (simplified to single
// representative codes). Population membership is Boolean-per-patient:
//   Initial Population: women 23-64 at period start with an office visit
//   Denominator: equals Initial Population
//   Denominator Exclusions: total hysterectomy OR hospice during the period
//   Numerator: cytology in the 3-year window OR HPV in the 5-year window
//
// Codes (real, instructional subset):
//   LOINC 10524-7  — cervical cytology (Pap)
//   LOINC 21440-3  — HPV DNA
//   SNOMED 116140006 — total hysterectomy (procedure)

define "Measurement Period":
  Interval[@2024-01-01, @2024-12-31]

define "Cytology Lookback":
  Interval[@2022-01-01, @2024-12-31]

define "HPV Lookback":
  Interval[@2020-01-01, @2024-12-31]

define "Is Female":
  Patient.gender = 'female'

define "Age At Start":
  AgeInYearsAt(start of "Measurement Period")

define "Had Office Visit":
  exists([Encounter] E where E.class.code = 'AMB' and E.period during "Measurement Period")

define "Initial Population":
  "Is Female" and "Age At Start" between 23 and 64 and "Had Office Visit"

define "Denominator":
  "Initial Population"

define "Had Hysterectomy":
  exists([Procedure] P where exists(P.code.coding cod where cod.code = '116140006' and cod.system = 'http://snomed.info/sct'))

define "In Hospice":
  exists([Encounter] E where E.class.code = 'HH' and E.period during "Measurement Period")

define "Denominator Exclusion":
  "Denominator" and ("Had Hysterectomy" or "In Hospice")

define "Had Recent Cytology":
  exists([Observation] O where exists(O.code.coding cod where cod.code = '10524-7' and cod.system = 'http://loinc.org') and (O.effective as FHIR.dateTime) during "Cytology Lookback")

define "Had Recent HPV":
  exists([Observation] O where exists(O.code.coding cod where cod.code = '21440-3' and cod.system = 'http://loinc.org') and (O.effective as FHIR.dateTime) during "HPV Lookback")

define "Numerator":
  "Denominator" and not "Denominator Exclusion" and ("Had Recent Cytology" or "Had Recent HPV")
