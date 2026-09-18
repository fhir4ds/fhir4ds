library MeasureBuilding version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// The capstone: a real eCQM shape. Five patients exercise every branch:
//   Alice: diabetic, 38, office visit, A1c        -> numerator
//   Bob:   diabetic, 51, office visit, A1c, HOSPICE -> excluded
//   Cara:  not diabetic (age 25, has visit + A1c)  -> not in IP
//   David: diabetic but 83                          -> not in IP (age)
//   Eve:   diabetic, 43, but NO office visit        -> IP but not denominator
//
// The measure: "Diabetes patients with a recent HbA1c test".

define "Measurement Period":
  Interval[@2024-01-01, @2024-12-31]

// TODO: "Has Diabetes" must be true when any Condition carries SNOMED
//   code 44054006 (match code AND system)
// TODO: "Age At Start" must compute age at the start of the period
// TODO: "Initial Population" must require diabetes AND age 18-75 inclusive
// TODO: "Had Office Visit" must be true when an AMB encounter's whole
//   period falls inside the measurement period
// TODO: "In Hospice" must detect Encounter class 'HH' during the period
// TODO: "Denominator" must be Initial Population AND office visit
// TODO: "Denominator Exclusion" must be Denominator AND hospice
// TODO: "Has Recent A1c" must find LOINC 4548-4 observations effective
//   during the period (cast the effective choice type!)
// TODO: "Numerator" must be Denominator AND NOT exclusion AND A1c —
//   Bob has an A1c but hospice excludes him
