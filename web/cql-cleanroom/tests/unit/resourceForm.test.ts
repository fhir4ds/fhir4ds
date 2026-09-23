/**
 * C3-U1: resourceForm pure-helper tests (INV-C3-3 round-trip, INV-C3-6
 * preview==payload discipline, absent≠empty semantics).
 */
import { describe, expect, it } from "vitest";
import {
  choiceKey,
  emptyForm,
  formToJson,
  isPrimitive,
  isRepeatable,
  jsonToForm,
} from "../../src/lib/resourceForm";
import type { SchemaField } from "../../src/lib/protocol";

const PATIENT_FIELDS: SchemaField[] = [
  { name: "id", types: ["string"], cardinality: "0..1", choice: false, reference_targets: [] },
  { name: "active", types: ["boolean"], cardinality: "0..1", choice: false, reference_targets: [] },
  { name: "gender", types: ["code"], cardinality: "0..1", choice: false, reference_targets: [] },
  { name: "birthDate", types: ["date"], cardinality: "0..1", choice: false, reference_targets: [] },
  { name: "multipleBirthInteger", types: ["integer"], cardinality: "0..1", choice: false, reference_targets: [] },
  { name: "name", types: ["HumanName"], cardinality: "0..*", choice: false, reference_targets: [] },
  { name: "address", types: ["Address"], cardinality: "0..*", choice: false, reference_targets: [] },
  { name: "deceased[x]", types: ["boolean", "dateTime"], cardinality: "0..1", choice: true, reference_targets: [] },
  { name: "generalPractitioner", types: ["Reference"], cardinality: "0..*", choice: false, reference_targets: ["Organization", "Practitioner"] },
];

const OBSERVATION_FIELDS: SchemaField[] = [
  { name: "id", types: ["string"], cardinality: "0..1", choice: false, reference_targets: [] },
  { name: "status", types: ["code"], cardinality: "1..1", choice: false, reference_targets: [] },
  { name: "value[x]", types: ["Quantity", "CodeableConcept", "string", "boolean"], cardinality: "0..1", choice: true, reference_targets: [] },
  { name: "effective[x]", types: ["dateTime", "Period"], cardinality: "0..1", choice: true, reference_targets: [] },
  { name: "subject", types: ["Reference"], cardinality: "0..1", choice: false, reference_targets: ["Patient", "Group"] },
];

describe("C3-U1 formToJson", () => {
  it("empty fields are ABSENT, not empty strings (preview==payload)", () => {
    const form = emptyForm("Patient");
    form.values.id = "p1";
    const json = formToJson(form, PATIENT_FIELDS);
    expect(json).toEqual({ resourceType: "Patient", id: "p1" });
  });

  it("coerces booleans and integers by schema type", () => {
    const form = emptyForm("Patient");
    form.values.id = "p9";
    form.values.active = "true";
    form.values.multipleBirthInteger = "3";
    const json = formToJson(form, PATIENT_FIELDS) as any;
    expect(json.active).toBe(true);
    expect(json.multipleBirthInteger).toBe(3);
  });

  it("repeatable fields emit arrays with empty rows dropped", () => {
    const form = emptyForm("Patient");
    form.values.generalPractitioner = ["Organization/o1", ""];
    const json = formToJson(form, PATIENT_FIELDS) as any;
    expect(json.generalPractitioner).toEqual(["Organization/o1"]);
  });

  it("choice fields emit the chosen concrete key", () => {
    const form = emptyForm("Observation");
    form.choices["value[x]"] = "string";
    form.values["value[x]"] = "severe";
    const json = formToJson(form, OBSERVATION_FIELDS) as any;
    expect(json.valueString).toBe("severe");
    expect("value[x]" in json).toBe(false);
  });

  it("passthrough merges back verbatim and survives round-trips", () => {
    const original = {
      resourceType: "Patient",
      id: "p1",
      gender: "female",
      name: [{ given: ["Ann"], family: "Doe" }],
      meta: { versionId: "2", lastUpdated: "2026-01-01T00:00:00Z" },
      unknownExtension: { deep: [1, 2, { x: true }] },
    };
    const form = jsonToForm(original, PATIENT_FIELDS);
    expect(form.values.gender).toBe("female");
    expect(form.passthrough.name).toEqual(original.name);
    expect(form.passthrough.meta).toEqual(original.meta);
    expect(form.passthrough.unknownExtension).toEqual(original.unknownExtension);
    const round = formToJson(form, PATIENT_FIELDS);
    expect(round).toEqual(original); // INV-C3-3: no silent data loss
  });

  it("scalar choice arm prefills; object choice arm passes through", () => {
    const withQuantity = {
      resourceType: "Observation",
      status: "final",
      valueQuantity: { value: 120, unit: "mmHg" },
    };
    const form = jsonToForm(withQuantity, OBSERVATION_FIELDS);
    expect(form.passthrough.valueQuantity).toEqual({ value: 120, unit: "mmHg" });
    const round = formToJson(form, OBSERVATION_FIELDS);
    expect(round).toEqual(withQuantity);

    const withString = {
      resourceType: "Observation",
      status: "final",
      valueString: "severe",
    };
    const form2 = jsonToForm(withString, OBSERVATION_FIELDS);
    expect(form2.choices["value[x]"]).toBe("string");
    expect(form2.values["value[x]"]).toBe("severe");
    expect(formToJson(form2, OBSERVATION_FIELDS)).toEqual(withString);
  });
});

describe("C3-U1 helpers", () => {
  it("choiceKey maps value[x] + Quantity → valueQuantity", () => {
    expect(choiceKey("value[x]", "Quantity")).toBe("valueQuantity");
    expect(choiceKey("deceased[x]", "dateTime")).toBe("deceasedDateTime");
  });

  it("isPrimitive / isRepeatable classify schema fields", () => {
    expect(isPrimitive(["code"])).toBe(true);
    expect(isPrimitive(["Reference"])).toBe(false);
    expect(isRepeatable("0..*")).toBe(true);
    expect(isRepeatable("0..1")).toBe(false);
  });
});
