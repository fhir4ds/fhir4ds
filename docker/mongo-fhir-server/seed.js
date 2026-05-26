const fhirDb = db.getSiblingDB("fhir");

fhirDb.Patient_4_0_0.deleteMany({ id: /^fhir4ds-mongo-/ });
fhirDb.Observation_4_0_0.deleteMany({ id: /^fhir4ds-mongo-/ });

fhirDb.Patient_4_0_0.insertOne({
  resourceType: "Patient",
  id: "fhir4ds-mongo-patient",
  active: true,
  name: [{ family: "FHIR4DS" }]
});

fhirDb.Observation_4_0_0.insertOne({
  resourceType: "Observation",
  id: "fhir4ds-mongo-observation",
  status: "final",
  subject: { reference: "Patient/fhir4ds-mongo-patient" },
  code: {
    coding: [
      {
        system: "http://loinc.org",
        code: "8480-6",
        display: "Systolic blood pressure"
      }
    ]
  },
  valueQuantity: {
    value: 120,
    unit: "mm[Hg]",
    system: "http://unitsofmeasure.org",
    code: "mm[Hg]"
  }
});

print("Seeded fhir4ds Mongo FHIR fixture");
