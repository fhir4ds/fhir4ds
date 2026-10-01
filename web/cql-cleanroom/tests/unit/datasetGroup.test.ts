import { describe, expect, it } from "vitest";
import {
  attributionWhy,
  groupDataset,
} from "../../src/lib/datasetGroup";

const P1 = { resourceType: "Patient", id: "p1", gender: "female" };
const P2 = { resourceType: "Patient", id: "p2", gender: "male" };
const OBS_P1 = {
  resourceType: "Observation",
  id: "o1",
  status: "final",
  code: { text: "bp" },
  subject: { reference: "Patient/p1" },
};
const ORG = { resourceType: "Organization", id: "org-1", name: "Acme" };
const OBS_GROUP = {
  resourceType: "Observation",
  id: "o2",
  subject: { reference: "Group/g7" },
};
const OBS_UUID = {
  resourceType: "Observation",
  id: "o3",
  subject: { reference: "urn:uuid:11111111-2222-3333-4444-555555555555" },
};

describe("groupDataset (0.0.18b §3.2)", () => {
  it("groups attributed resources under their Patient", () => {
    const groups = groupDataset([P1, OBS_P1, ORG]);
    expect(groups.map((g) => g.key)).toEqual(["p1", "__unattributed__"]);
    const p1 = groups[0];
    expect(p1.rows.map((r) => r.id)).toEqual(["p1", "o1"]);
    expect(p1.rows.map((r) => r.index)).toEqual([0, 1]); // flat storage identity
  });

  it("orders: Patient groups alphabetical, phantoms after, Unattributed last (F6)", () => {
    const groups = groupDataset([OBS_UUID, P2, P1, OBS_GROUP, ORG]);
    expect(groups.map((g) => g.key)).toEqual([
      "p1",
      "p2",
      "11111111-2222-3333-4444-555555555555",
      "__unattributed__",
    ]);
    expect(groups[2].phantom).toBe(true);
    expect(groups[3].unattributed).toBe(true);
  });

  it("keeps flat storage indices when display order differs", () => {
    // Storage order: ORG(0), P1(1), OBS_P1(2) — display groups reorder.
    const groups = groupDataset([ORG, P1, OBS_P1]);
    expect(groups.map((g) => g.key)).toEqual(["p1", "__unattributed__"]);
    const p1 = groups[0];
    expect(p1.rows.map((r) => r.index)).toEqual([1, 2]);
    expect(groups[1].rows[0].index).toBe(0);
  });

  it("phantom group holds uuid-keyed rows without a Patient resource", () => {
    const groups = groupDataset([OBS_UUID]);
    expect(groups).toHaveLength(1);
    expect(groups[0].phantom).toBe(true);
    expect(groups[0].rows[0].id).toBe("o3");
  });

  it("a Patient resource with the same id absorbs the phantom", () => {
    const uuid = "11111111-2222-3333-4444-555555555555";
    const patient = { resourceType: "Patient", id: uuid };
    const groups = groupDataset([OBS_UUID, patient]);
    expect(groups).toHaveLength(1);
    expect(groups[0].phantom).toBe(false);
    expect(groups[0].key).toBe(uuid);
  });
});

describe("attributionWhy (S-3)", () => {
  it("explains Group-targeted subjects", () => {
    expect(attributionWhy(OBS_GROUP)).toContain("Group/g7");
  });

  it("explains bare-id references", () => {
    const r = { resourceType: "Observation", subject: { reference: "p1" } };
    expect(attributionWhy(r)).toContain("bare id");
  });

  it("explains urn:uuid phantoms", () => {
    expect(attributionWhy(OBS_UUID)).toContain("urn:uuid phantom");
  });

  it("explains reference-field-free resources", () => {
    const why = attributionWhy(ORG);
    expect(why).toContain("subject/patient/beneficiary");
  });

  it("explains missing Patient id", () => {
    const why = attributionWhy({ resourceType: "Patient" });
    expect(why).toContain("id");
  });
});
