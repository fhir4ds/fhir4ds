export interface CQLSample {
  id: string;
  label: string;
  cql: string;
  description: string;
  /** If true, this sample appears in the "Common Core" set shown in smart-flow */
  commonCore?: boolean;
}

export const CQL_SAMPLES: CQLSample[] = [
  {
    id: "clinical-overview",
    label: "Clinical Overview",
    description: "Comprehensive patient summary: name, age, active conditions, medications, and procedures",
    commonCore: true,
    cql: `library ClinicalOverview version '1.0.0'

using FHIR version '4.0.1'

context Patient

define "Patient Name":
  Patient.name.family.first()

define "Birth Date":
  Patient.birthDate

define "Gender":
  Patient.gender

define "All Conditions":
  [Condition] C where C.id is not null

define "Condition Count":
  Count("All Conditions")

define "All Medications":
  [MedicationRequest] M where M.id is not null

define "Medication Count":
  Count("All Medications")

define "All Procedures":
  [Procedure] P where P.id is not null

define "Procedure Count":
  Count("All Procedures")

define "All Encounters":
  [Encounter] E where E.id is not null

define "Encounter Count":
  Count("All Encounters")`,
  },
  {
    id: "patient-demographics",
    label: "Patient Demographics",
    description: "Simple query to retrieve patient names and birth dates",
    cql: `library PatientDemographics version '1.0.0'

using FHIR version '4.0.1'

context Patient

// Use .first() so the postprocessSQL step strips list_extract() wrappers
// and leaves a clean fhirpath_text(resource, 'name.family') call.
define "Patient Name":
  Patient.name.family.first()

define "Birth Date":
  Patient.birthDate

define "Gender":
  Patient.gender`,
  },
  {
    id: "active-conditions",
    label: "Active Conditions",
    description: "Find patients with active conditions and their codes",
    cql: `library ActiveConditions version '1.0.0'

using FHIR version '4.0.1'

context Patient

define "Active Conditions":
  [Condition] C
    where exists(C.clinicalStatus.coding C2 where C2.code = 'active')

define "Has Active Condition":
  exists "Active Conditions"

define "Active Condition Count":
  Count("Active Conditions")`,
  },
  {
    id: "diabetes-screening",
    label: "Diabetes Screening Measure",
    description:
      "Population measure: identify diabetic patients and retrieve their most recent HbA1c result",
    commonCore: true,
    cql: `library DiabetesScreening version '1.0.0'

using FHIR version '4.0.1'

context Patient

define "Diabetes Diagnosis":
  [Condition] C
    where exists(C.code.coding C2
      where C2.system = 'http://snomed.info/sct'
        and C2.code = '73211009')

define "Initial Population":
  exists "Diabetes Diagnosis"

define "Has Recent Encounter":
  exists [Encounter] E
    where E.status = 'finished'

define "Denominator":
  "Initial Population" and "Has Recent Encounter"

define "HbA1c Observations":
  [Observation] O
    where exists(O.code.coding C2
      where C2.system = 'http://loinc.org'
        and C2.code = '4548-4')

define "Has HbA1c Test":
  exists "HbA1c Observations"

define "Most Recent HbA1c Value":
  First("HbA1c Observations" O sort by effectiveDateTime descending).valueQuantity.value

define "Numerator":
  "Denominator" and "Has HbA1c Test"`,
  },
  {
    id: "vital-signs",
    label: "Vital Signs & Observations",
    description:
      "Demonstrates mixed return types: numeric values, strings, booleans, dates, and observation counts",
    commonCore: true,
    cql: `library VitalSigns version '1.0.0'

using FHIR version '4.0.1'

context Patient

define "Birth Date":
  Patient.birthDate

define "Gender":
  Patient.gender

define "BP Observations":
  [Observation] O
    where exists(O.code.coding C where C.code = '8480-6')

define "Latest Systolic BP":
  First("BP Observations" O sort by effectiveDateTime descending).valueQuantity.value

define "BP Status":
  First("BP Observations" O sort by effectiveDateTime descending).status

define "Has High BP":
  exists [Observation] O
    where exists(O.code.coding C where C.code = '8480-6')
      and O.valueQuantity.value > 140

define "Observation Count":
  Count([Observation] O where O.status = 'final')

define "Has Any Vital Sign":
  exists [Observation] O
    where O.status = 'final'`,
  },
];
