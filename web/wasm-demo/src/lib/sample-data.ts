// Synthetic FHIR R4 resources for the demo.
// 10 patients with related Conditions, Observations, and Encounters.

export const SAMPLE_RESOURCES: Record<string, unknown>[] = [
  // ── Patients ──
  {
    resourceType: "Patient",
    id: "patient-001",
    name: [{ given: ["Alice"], family: "Johnson" }],
    gender: "female",
    birthDate: "1985-03-12",
  },
  {
    resourceType: "Patient",
    id: "patient-002",
    name: [{ given: ["Bob"], family: "Smith" }],
    gender: "male",
    birthDate: "1972-07-23",
  },
  {
    resourceType: "Patient",
    id: "patient-003",
    name: [{ given: ["Carol"], family: "Williams" }],
    gender: "female",
    birthDate: "1990-11-05",
  },
  {
    resourceType: "Patient",
    id: "patient-004",
    name: [{ given: ["David"], family: "Brown" }],
    gender: "male",
    birthDate: "1968-01-30",
  },
  {
    resourceType: "Patient",
    id: "patient-005",
    name: [{ given: ["Eve"], family: "Davis" }],
    gender: "female",
    birthDate: "1995-06-18",
  },
  {
    resourceType: "Patient",
    id: "patient-006",
    name: [{ given: ["Frank"], family: "Miller" }],
    gender: "male",
    birthDate: "1980-09-02",
  },
  {
    resourceType: "Patient",
    id: "patient-007",
    name: [{ given: ["Grace"], family: "Wilson" }],
    gender: "female",
    birthDate: "1977-04-14",
  },
  {
    resourceType: "Patient",
    id: "patient-008",
    name: [{ given: ["Henry"], family: "Moore" }],
    gender: "male",
    birthDate: "1960-12-25",
  },
  {
    resourceType: "Patient",
    id: "patient-009",
    name: [{ given: ["Iris"], family: "Taylor" }],
    gender: "female",
    birthDate: "1988-08-09",
  },
  {
    resourceType: "Patient",
    id: "patient-010",
    name: [{ given: ["Jack"], family: "Anderson" }],
    gender: "male",
    birthDate: "2001-02-28",
  },

  // ── Conditions ──
  {
    resourceType: "Condition",
    id: "condition-001",
    subject: { reference: "Patient/patient-002" },
    code: {
      coding: [
        { system: "http://snomed.info/sct", code: "73211009", display: "Diabetes mellitus" },
      ],
    },
    clinicalStatus: { coding: [{ code: "active" }] },
    onsetDateTime: "2015-06-15",
  },
  {
    resourceType: "Condition",
    id: "condition-002",
    subject: { reference: "Patient/patient-004" },
    code: {
      coding: [
        { system: "http://snomed.info/sct", code: "73211009", display: "Diabetes mellitus" },
      ],
    },
    clinicalStatus: { coding: [{ code: "active" }] },
    onsetDateTime: "2018-03-22",
  },
  {
    resourceType: "Condition",
    id: "condition-003",
    subject: { reference: "Patient/patient-001" },
    code: {
      coding: [
        { system: "http://snomed.info/sct", code: "38341003", display: "Hypertension" },
      ],
    },
    clinicalStatus: { coding: [{ code: "active" }] },
    onsetDateTime: "2020-01-10",
  },
  {
    resourceType: "Condition",
    id: "condition-004",
    subject: { reference: "Patient/patient-006" },
    code: {
      coding: [
        { system: "http://snomed.info/sct", code: "195967001", display: "Asthma" },
      ],
    },
    clinicalStatus: { coding: [{ code: "active" }] },
    onsetDateTime: "2010-08-05",
  },
  {
    resourceType: "Condition",
    id: "condition-005",
    subject: { reference: "Patient/patient-008" },
    code: {
      coding: [
        { system: "http://snomed.info/sct", code: "73211009", display: "Diabetes mellitus" },
      ],
    },
    clinicalStatus: { coding: [{ code: "resolved" }] },
    onsetDateTime: "2012-11-20",
  },

  // ── Observations (HbA1c tests) ──
  {
    resourceType: "Observation",
    id: "obs-001",
    subject: { reference: "Patient/patient-002" },
    code: {
      coding: [
        { system: "http://loinc.org", code: "4548-4", display: "Hemoglobin A1c" },
      ],
    },
    status: "final",
    valueQuantity: { value: 7.2, unit: "%", system: "http://unitsofmeasure.org", code: "%" },
    effectiveDateTime: "2025-01-15",
  },
  {
    resourceType: "Observation",
    id: "obs-002",
    subject: { reference: "Patient/patient-004" },
    code: {
      coding: [
        { system: "http://loinc.org", code: "4548-4", display: "Hemoglobin A1c" },
      ],
    },
    status: "final",
    valueQuantity: { value: 8.1, unit: "%", system: "http://unitsofmeasure.org", code: "%" },
    effectiveDateTime: "2025-03-20",
  },
  {
    resourceType: "Observation",
    id: "obs-003",
    subject: { reference: "Patient/patient-001" },
    code: {
      coding: [
        { system: "http://loinc.org", code: "8480-6", display: "Systolic blood pressure" },
      ],
    },
    status: "final",
    valueQuantity: { value: 142, unit: "mmHg", system: "http://unitsofmeasure.org", code: "mm[Hg]" },
    effectiveDateTime: "2025-02-10",
  },
  {
    resourceType: "Observation",
    id: "obs-004",
    subject: { reference: "Patient/patient-005" },
    code: {
      coding: [
        { system: "http://loinc.org", code: "29463-7", display: "Body weight" },
      ],
    },
    status: "final",
    valueQuantity: { value: 68, unit: "kg", system: "http://unitsofmeasure.org", code: "kg" },
    effectiveDateTime: "2025-04-01",
  },

  // Body temperature – patient-003
  {
    resourceType: "Observation",
    id: "obs-005",
    subject: { reference: "Patient/patient-003" },
    code: {
      coding: [
        { system: "http://loinc.org", code: "8310-5", display: "Body temperature" },
      ],
    },
    status: "final",
    valueQuantity: { value: 99.2, unit: "°F", system: "http://unitsofmeasure.org", code: "[degF]" },
    effectiveDateTime: "2025-03-15",
  },
  // BMI – patient-006
  {
    resourceType: "Observation",
    id: "obs-006",
    subject: { reference: "Patient/patient-006" },
    code: {
      coding: [
        { system: "http://loinc.org", code: "39156-5", display: "Body mass index" },
      ],
    },
    status: "final",
    valueQuantity: { value: 28.5, unit: "kg/m2", system: "http://unitsofmeasure.org", code: "kg/m2" },
    effectiveDateTime: "2025-01-20",
  },
  // Systolic BP – patient-007
  {
    resourceType: "Observation",
    id: "obs-007",
    subject: { reference: "Patient/patient-007" },
    code: {
      coding: [
        { system: "http://loinc.org", code: "8480-6", display: "Systolic blood pressure" },
      ],
    },
    status: "final",
    valueQuantity: { value: 128, unit: "mmHg", system: "http://unitsofmeasure.org", code: "mm[Hg]" },
    effectiveDateTime: "2025-02-28",
  },
  // Body weight – patient-009
  {
    resourceType: "Observation",
    id: "obs-008",
    subject: { reference: "Patient/patient-009" },
    code: {
      coding: [
        { system: "http://loinc.org", code: "29463-7", display: "Body weight" },
      ],
    },
    status: "final",
    valueQuantity: { value: 72, unit: "kg", system: "http://unitsofmeasure.org", code: "kg" },
    effectiveDateTime: "2025-04-10",
  },

  // ── Encounters ──
  {
    resourceType: "Encounter",
    id: "enc-001",
    subject: { reference: "Patient/patient-002" },
    status: "finished",
    class: { code: "AMB" },
    period: { start: "2025-01-15", end: "2025-01-15" },
  },
  {
    resourceType: "Encounter",
    id: "enc-002",
    subject: { reference: "Patient/patient-004" },
    status: "finished",
    class: { code: "AMB" },
    period: { start: "2025-03-20", end: "2025-03-20" },
  },
  {
    resourceType: "Encounter",
    id: "enc-003",
    subject: { reference: "Patient/patient-001" },
    status: "finished",
    class: { code: "AMB" },
    period: { start: "2025-02-10", end: "2025-02-10" },
  },
  {
    resourceType: "Encounter",
    id: "enc-004",
    subject: { reference: "Patient/patient-006" },
    status: "finished",
    class: { code: "AMB" },
    period: { start: "2024-12-01", end: "2024-12-01" },
  },
  {
    resourceType: "Encounter",
    id: "enc-005",
    subject: { reference: "Patient/patient-008" },
    status: "in-progress",
    class: { code: "IMP" },
    period: { start: "2025-04-01" },
  },
];
