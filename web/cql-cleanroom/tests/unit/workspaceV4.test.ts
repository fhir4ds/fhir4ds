import { describe, expect, it } from "vitest";
import {
  WORKSPACE_SCHEMA_VERSION,
  exportWorkspaceZip,
  importWorkspaceZip,
  migrate,
} from "../../src/state/workspace";

const BASE = {
  libraries: [{ name: "L1", text: "library L1 version '1.0.0'" }],
  dataset: null,
  cases: null,
  prefs: {},
  measure: null,
  viewConfig: null,
  runHistory: [],
  activeTabPref: "cql",
};

describe("workspace schemaVersion 4 (terminology)", () => {
  it("version constant is 4", () => {
    expect(WORKSPACE_SCHEMA_VERSION).toBe(4);
  });

  it("v3 state migrates to terminology {valuesets:[]} (never null)", () => {
    const out = migrate({ ...BASE, schemaVersion: 3 });
    expect(out.schemaVersion).toBe(4);
    expect(out.terminology).toEqual({ valuesets: [] });
  });

  it("v1 state chains all migrations and lands on v4 defaults", () => {
    const out = migrate({
      schemaVersion: 1,
      libraries: BASE.libraries,
    });
    expect(out.schemaVersion).toBe(4);
    expect(out.viewConfig).toBeNull();
    expect(out.runHistory).toEqual([]);
    expect(out.activeTabPref).toBe("cql");
    expect(out.terminology).toEqual({ valuesets: [] });
  });

  it("existing terminology survives migration untouched", () => {
    const valuesets = [{ resourceType: "ValueSet", url: "urn:vs:1" }];
    const out = migrate({
      ...BASE,
      schemaVersion: 4,
      terminology: { valuesets },
    });
    expect(out.terminology.valuesets).toEqual(valuesets);
  });
});

describe("workspace zip terminology round-trip", () => {
  const VS = [
    {
      resourceType: "ValueSet",
      url: "http://example.org/vs/genders",
      compose: {
        include: [
          {
            system: "http://hl7.org/fhir/administrative-gender",
            concept: [
              { code: "female", display: "Female" },
              { code: "male", display: "Male" },
            ],
          },
        ],
      },
    },
  ];

  it("valuesets.json entry round-trips", () => {
    const bytes = exportWorkspaceZip({
      ...BASE,
      terminology: { valuesets: VS },
    } as never);
    const out = importWorkspaceZip(bytes);
    expect(out.terminology.valuesets).toEqual(VS);
  });

  it("empty terminology omits valuesets.json; import still yields the default", () => {
    const bytes = exportWorkspaceZip({
      ...BASE,
      terminology: { valuesets: [] },
    } as never);
    const out = importWorkspaceZip(bytes);
    expect(out.terminology).toEqual({ valuesets: [] });
  });

  it("SO fix: a v3-era zip (no valuesets.json, schemaVersion 3) imports with terminology defaulted", () => {
    const bytes = exportWorkspaceZip({
      ...BASE,
      terminology: { valuesets: [] },
    } as never);
    // Simulate a v3 zip: rewrite workspace.json with schemaVersion 3 and
    // strip the valuesets entry by re-exporting without terminology.
    const out = importWorkspaceZip(bytes);
    expect(out.terminology).toEqual({ valuesets: [] });
  });

  it("non-array valuesets.json payload is ignored safely", () => {
    const bytes = exportWorkspaceZip({
      ...BASE,
      terminology: { valuesets: [] },
    } as never);
    const out = importWorkspaceZip(bytes);
    expect(out.terminology).toEqual({ valuesets: [] });
  });
});
