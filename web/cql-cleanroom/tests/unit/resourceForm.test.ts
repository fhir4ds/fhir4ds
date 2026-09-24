/**
 * v2 recursive form-model tests (FEATURE_CLEANROOM_TEST_DATA_AUTHORING §3.3):
 * round-trip losslessness at depth (INV-5), Reference objects not scalars
 * (F4), persistent _key passthrough attachment (F2), per-level hatches,
 * absent≠"" discipline, array/choice emit semantics.
 */
import { describe, expect, it } from "vitest";
import {
  choiceKey,
  emptyForm,
  emptyObject,
  formToJson,
  isPrimitiveType,
  isRepeatable,
  jsonToForm,
  newKey,
} from "../../src/lib/resourceForm";
import type { SchemaTreeNode } from "../../src/lib/protocol";

const n = (
  name: string,
  type: string,
  cardinality = "0..1",
  extra: Partial<SchemaTreeNode> = {},
): SchemaTreeNode => ({ name, type, cardinality, ...extra });

function patientTree(): SchemaTreeNode {
  return {
    name: "Patient",
    type: "Patient",
    cardinality: "0..1",
    children: [
      n("id", "string"),
      n("active", "boolean"),
      n("gender", "code"),
      n("birthDate", "date"),
      n("multipleBirthInteger", "integer"),
      {
        name: "name",
        type: "HumanName",
        cardinality: "0..*",
        children: [
          n("family", "string"),
          { name: "given", type: "string", cardinality: "0..*", children: [] },
        ],
      },
      n("deceasedBoolean", "boolean"),
      n("deceasedDateTime", "dateTime"),
      {
        name: "generalPractitioner",
        type: "Reference",
        cardinality: "0..*",
        reference_targets: ["Organization", "Practitioner"],
      },
      {
        name: "subject",
        type: "Reference",
        reference_targets: ["Patient"],
        children: [],
      },
      { name: "meta", type: "Meta", children: [n("versionId", "string")] },
    ],
  };
}

function observationTree(): SchemaTreeNode {
  return {
    name: "Observation",
    type: "Observation",
    children: [
      n("status", "code", "1..1"),
      n("valueString", "string"),
      {
        name: "valueQuantity",
        type: "Quantity",
        children: [
          n("value", "decimal"),
          n("unit", "string"),
          n("system", "uri"),
          n("code", "code"),
        ],
      },
      n("effectiveDateTime", "dateTime"),
      {
        name: "component",
        type: "BackboneElement",
        cardinality: "0..*",
        children: [
          {
            name: "code",
            type: "CodeableConcept",
            children: [
              {
                name: "coding",
                type: "Coding",
                cardinality: "0..*",
                children: [
                  n("system", "uri"),
                  n("code", "code"),
                  n("display", "string"),
                ],
              },
              n("text", "string"),
            ],
          },
          n("valueBoolean", "boolean"),
        ],
      },
    ],
  };
}

describe("v2 formToJson", () => {
  it("empty fields are ABSENT, not empty strings (preview==payload)", () => {
    const form = emptyForm("Patient");
    form.values.id = { kind: "scalar", value: "p1" };
    const json = formToJson(form, patientTree());
    expect(json).toEqual({ resourceType: "Patient", id: "p1" });
  });

  it("coerces booleans/integers/decimals by node type", () => {
    const form = emptyForm("Patient");
    form.values.active = { kind: "scalar", value: "true" };
    form.values.multipleBirthInteger = { kind: "scalar", value: "3" };
    const json = formToJson(form, patientTree()) as any;
    expect(json.active).toBe(true);
    expect(json.multipleBirthInteger).toBe(3);
  });

  it("nested complex values emit deep objects", () => {
    const form = emptyForm("Patient");
    form.values.name = {
      kind: "items",
      items: [
        {
          key: newKey(),
          value: {
            kind: "object",
            children: {
              family: { kind: "scalar", value: "Doe" },
              given: {
                kind: "items",
                items: [
                  { key: newKey(), value: { kind: "scalar", value: "Ann" } },
                  { key: newKey(), value: { kind: "scalar", value: "" } },
                ],
              },
            },
            passthrough: {},
          },
        },
      ],
    };
    const json = formToJson(form, patientTree()) as any;
    expect(json.name).toEqual([{ family: "Doe", given: ["Ann"] }]);
  });

  it("references emit {reference} OBJECTS, never scalar strings (F4)", () => {
    const form = emptyForm("Patient");
    form.values.generalPractitioner = {
      kind: "items",
      items: [
        { key: newKey(), value: { kind: "ref", reference: "Organization/o1" } },
        { key: newKey(), value: { kind: "ref", reference: "" } },
      ],
    };
    const json = formToJson(form, patientTree()) as any;
    expect(json.generalPractitioner).toEqual([
      { reference: "Organization/o1" },
    ]);
  });

  it("top-level passthrough merges back verbatim", () => {
    const form = emptyForm("Patient");
    form.passthrough.text = { div: "<p>hi</p>" };
    const json = formToJson(form, patientTree()) as any;
    expect(json.text).toEqual({ div: "<p>hi</p>" });
  });
});

describe("v2 jsonToForm round-trips (INV-5)", () => {
  it("deep resources round-trip losslessly with unknown keys at depth", () => {
    const original = {
      resourceType: "Observation",
      status: "final",
      valueQuantity: { value: 120, unit: "mmHg", unknownDeep: [1, 2] },
      component: [
        {
          code: { coding: [{ system: "http://loinc.org", code: "8480-6" }] },
          valueBoolean: true,
          notModeled: "kept",
        },
      ],
      meta: { versionId: "2", extra: { x: 1 } },
    };
    const form = jsonToForm(original, observationTree());
    const round = formToJson(form, observationTree());
    expect(round).toEqual(original);
  });

  it("Reference OBJECTS prefill to ref values (F4 inverse)", () => {
    const original = {
      resourceType: "Patient",
      subject: { reference: "Patient/p9", display: "Self" },
    };
    const form = jsonToForm(original, patientTree());
    expect(form.values.subject).toEqual({
      kind: "ref",
      reference: "Patient/p9",
      display: "Self",
    });
    expect(formToJson(form, patientTree())).toEqual(original);
  });

  it("scalar string in a Reference slot hatches (malformed input)", () => {
    const original = {
      resourceType: "Patient",
      subject: "Patient/p9", // scalar string — NOT a Reference object
    };
    const form = jsonToForm(original, patientTree());
    const v = form.values.subject;
    expect(v?.kind).toBe("hatch");
    expect(formToJson(form, patientTree())).toEqual(original);
  });

  it("unknown top-level keys land in top-level passthrough", () => {
    const original = {
      resourceType: "Patient",
      id: "p1",
      gender: "female",
      contained: [{ resourceType: "Organization", id: "o1" }],
    };
    const form = jsonToForm(original, patientTree());
    expect(form.values.id).toEqual({ kind: "scalar", value: "p1" });
    expect(form.passthrough.contained).toEqual(original.contained);
    expect(formToJson(form, patientTree())).toEqual(original);
  });

  it("choice arms (valueQuantity/valueString) map to their own nodes", () => {
    const withQuantity = {
      resourceType: "Observation",
      status: "final",
      valueQuantity: { value: 120, unit: "mmHg" },
    };
    const form = jsonToForm(withQuantity, observationTree());
    const q = form.values.valueQuantity;
    expect(q?.kind).toBe("object");
    expect(formToJson(form, observationTree())).toEqual(withQuantity);
  });

  it("repeatable singleton JSON becomes a 1-item list (normalized)", () => {
    const original = {
      resourceType: "Patient",
      name: { family: "Doe" }, // object where array expected
    };
    const form = jsonToForm(original, patientTree());
    const v = form.values.name;
    expect(v?.kind).toBe("items");
    expect(v?.kind === "items" && v.items).toHaveLength(1);
    // emit normalizes to the FHIR list shape
    expect(formToJson(form, patientTree())).toEqual({
      resourceType: "Patient",
      name: [{ family: "Doe" }],
    });
  });
});

describe("v2 helpers", () => {
  it("choiceKey maps value[x] + Quantity → valueQuantity", () => {
    expect(choiceKey("value[x]", "Quantity")).toBe("valueQuantity");
    expect(choiceKey("deceased[x]", "dateTime")).toBe("deceasedDateTime");
  });

  it("isPrimitiveType / isRepeatable classify nodes", () => {
    expect(isPrimitiveType("code")).toBe(true);
    expect(isPrimitiveType("Reference")).toBe(false);
    expect(isRepeatable("0..*")).toBe(true);
    expect(isRepeatable("0..1")).toBe(false);
    expect(isRepeatable(undefined)).toBe(false);
  });

  it("keys are unique and monotonic (F2 passthrough attachment)", () => {
    const seen = new Set<string>();
    for (let i = 0; i < 100; i++) {
      const k = newKey();
      expect(seen.has(k)).toBe(false);
      seen.add(k);
    }
  });

  it("emptyObject carries per-level passthrough", () => {
    const o = emptyObject();
    expect(o.kind).toBe("object");
    expect(o.children).toEqual({});
    expect(o.passthrough).toEqual({});
  });
});
