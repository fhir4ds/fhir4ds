/*
 * CMS125-style demo library (Breast Cancer Screening).
 *
 * SYNTHETIC implementation — NOT the copyrighted eCQM text. Inspired by
 * CMS125v2 "Breast Cancer Screening" (measure id 125; women 52-74 with
 * a mammogram during the measurement period or the 15 months prior).
 * Simplified logic consistent with the cleanroom's runtime-retrieval
 * pillar: valuesets are local workspace files under valuesets/.
 *
 * Defines use QUOTED human-styled names that match their cell markers
 * exactly (auto-cellify doctrine: marker name = define name).
 *
 * EXPECTED RESULTS on the bundled data/patients.ndjson (22 patients):
 *   Initial Population = 18 (women 52-74 with a preventive visit)
 *   Numerator          = 10 (subset with a mammogram in window)
 *   Excluded: 2 women too young (b. 1978), 2 men.
 * Note: the mammography valueset intentionally includes a SNOMED
 * DIAGNOSTIC mammo code for demo breadth — in the real measure only
 * screening codes count toward the numerator.
 */
library CMS125Demo version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

valueset "Mammography": 'http://example.org/cms125/mammography'
valueset "Preventive Encounter": 'http://example.org/cms125/preventive-encounter'

parameter "Measurement Period" Interval<DateTime>
  default Interval[@2024-01-01T00:00:00.0, @2024-12-31T23:59:59.999]

context Patient

// # %% [name: InAgeRange]
define "InAgeRange":
  AgeInYearsAt(start of "Measurement Period") >= 52
    and AgeInYearsAt(start of "Measurement Period") <= 74

// # %% [name: RecentMammogram]
define "RecentMammogram":
  exists (
    [Procedure: "Mammography"] P
      where P.status = 'completed'
        and P.performed during day of Interval[
              start of "Measurement Period" - 15 months,
              end of "Measurement Period"
            ]
  )

// # %% [name: PreventiveVisit]
define "PreventiveVisit":
  exists (
    [Encounter: "Preventive Encounter"] E
      where E.status = 'finished'
        and E.period."start" during day of "Measurement Period"
  )

// # %% [name: Initial Population]
define "Initial Population":
  Patient.gender = 'female'
    and "InAgeRange"
    and "PreventiveVisit"

// # %% [name: Numerator]
define "Numerator":
  "Initial Population"
    and "RecentMammogram"

// # %% [name: Summary]
define "Summary":
  Tuple {
    in_initial_population: "Initial Population",
    in_numerator: "Numerator",
    had_mammogram: "RecentMammogram"
  }
