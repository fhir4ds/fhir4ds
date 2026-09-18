library CervicalScreening version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// CMS124-shaped cervical cancer screening. Eight patients cover every
// branch of the measure:
//   Ana:   33, visit, cytology 2023              -> numerator (3y window)
//   Beth:  31, visit, HPV 2021                   -> numerator (5y window)
//   Cora:  22, visit, cytology 2024              -> NOT in IP (too young)
//   Dana:  43, visit, no screening at all        -> denominator only
//   Eve:   48, visit, cytology 2024, HYSTERECTOMY -> excluded
//   Faye:  38, visit, HPV 2019                   -> NOT numerator (outside 5y)
//   Gail:  53, visit, cytology 2024, HOSPICE     -> excluded
//   Hank:  male, 40, visit, cytology             -> NOT in IP
//
// Codes: cytology LOINC 10524-7, HPV LOINC 21440-3,
//        hysterectomy SNOMED 116140006.

define "Measurement Period":
  Interval[@2024-01-01, @2024-12-31]

// TODO: "Cytology Lookback" must span the period plus the two prior years
//   (a 3-year screening window)
// TODO: "HPV Lookback" must span the period plus the four prior years
//   (a 5-year screening window)
// TODO: "Is Female" must read the Patient's gender element
// TODO: "Age At Start" must compute age at the start of the period

define "Had Office Visit":
  exists([Encounter] E where E.class.code = 'AMB' and E.period during "Measurement Period")

// TODO: "Initial Population" must require female AND age 23-64 inclusive
//   AND an office visit
// TODO: "Denominator" equals the Initial Population
// TODO: "Had Hysterectomy" must find a Procedure with SNOMED 116140006
//   (match code AND system)

define "In Hospice":
  exists([Encounter] E where E.class.code = 'HH' and E.period during "Measurement Period")

// TODO: "Denominator Exclusion" must be Denominator AND (hysterectomy OR
//   hospice) — parenthesize the two exclusion paths
// TODO: "Had Recent Cytology" must find LOINC 10524-7 observations
//   effective during the cytology lookback (choice-type cast on effective)
// TODO: "Had Recent HPV" must find LOINC 21440-3 observations effective
//   during the HPV lookback
// TODO: "Numerator" must be Denominator, not excluded, with cytology OR
//   HPV screening
