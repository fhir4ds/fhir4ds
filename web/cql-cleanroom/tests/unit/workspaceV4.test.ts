import { describe, expect, it } from "vitest";
import { zipSync } from "fflate";
import {
  WORKSPACE_SCHEMA_VERSION,
  exportWorkspaceZip,
  importWorkspaceZip,
  migrate,
  newLibraryId,
  withLibraryIds,
} from "../../src/state/workspace";

const BASE_V5 = {
  libraries: [{ name: "L1", text: "library L1 version '1.0.0'" }],
  dataset: null,
  cases: null,
  prefs: {},
  measure: null,
  viewConfig: null,
  runHistory: [],
  activeTabPref: "cql",
  paramValues: {},
};

const MEASURE = {
  resourceType: "Measure",
  name: "CleanroomMeasure",
  status: "draft",
  group: [
    {
      population: [
        {
          code: { coding: [{ code: "initial-population" }] },
          criteria: { language: "text/cql-identifier", expression: "Initial Population" },
        },
      ],
    },
  ],
};

describe("workspace schemaVersion (WORKBENCH_V6 collections)", () => {
  it("version constant is 6", () => {
    expect(WORKSPACE_SCHEMA_VERSION).toBe(6);
  });

  it("v3 state chains all migrations and lands on v6 defaults", () => {
    const out = migrate({ ...BASE_V5, schemaVersion: 3 });
    expect(out.schemaVersion).toBe(6);
    expect(out.terminology).toEqual({ valuesets: [] });
    expect(out.measures).toEqual([]);
    expect(out.activeMeasureId).toBeNull();
    expect(out.expectedReports).toEqual({});
    expect(out.viewDefs).toEqual([]);
    expect(out.paramBindings).toEqual({});
    expect(out.runHistory).toEqual([]);
    expect(out.activeTabPref).toBe("cql");
  });

  it("v5 single measure becomes measures[0] pinned to the first library", () => {
    const out = migrate({
      ...BASE_V5,
      schemaVersion: 5,
      measure: MEASURE,
      paramValues: { "Measurement Period": "2026" },
    });
    expect(out.libraries[0].id).toBe("lib_0");
    expect(out.measures).toHaveLength(1);
    expect(out.measures[0].id).toBe("msr_0");
    expect(out.measures[0].mainLibraryId).toBe("lib_0");
    expect(out.measures[0].resource).toEqual(MEASURE);
    expect(out.activeMeasureId).toBe("msr_0");
    expect(out.paramBindings).toEqual({ msr_0: { "Measurement Period": "2026" } });
  });

  it("v5 viewConfig overrides seed a stored ViewDefinition AND ride along (legacy)", () => {
    const out = migrate({
      ...BASE_V5,
      schemaVersion: 5,
      measure: MEASURE,
      viewConfig: { overrides: { initial_population: { name: "IP" } } },
    });
    expect(out.viewDefs).toHaveLength(1);
    expect(out.viewDefs[0].id).toBe("vd_0");
    const cols = (out.viewDefs[0].resource.select as Array<{ column: Array<Record<string, unknown>> }>)[0]
      .column as Array<Record<string, unknown>>;
    expect(cols.find((c) => c.name === "IP")).toBeTruthy();
    // legacy field survives until the View pane goes stored-mode
    expect(out.viewConfig).toEqual({ overrides: { initial_population: { name: "IP" } } });
  });

  it("v5 case rows migrate into authored expectedReports for measures[0]", () => {
    const out = migrate({
      ...BASE_V5,
      schemaVersion: 5,
      measure: MEASURE,
      cases: [
        { patient: "p1", population: "initial-population", expect: true },
        { patient: "p1", population: "numerator", expect: false },
        { patient: "p2", population: "initial-population", expect: true },
      ],
    });
    const reports = out.expectedReports.msr_0;
    expect(reports).toHaveLength(2);
    const p1 = reports.find(
      (r) => (r.subject as { reference: string }).reference === "Patient/p1",
    );
    const pops = (p1!.group as Array<{ population: Array<{ code: { coding: Array<{ code: string }> }; count: number }> }>)[0]
      .population;
    expect(pops.find((p) => p.code.coding[0].code === "initial-population")!.count).toBe(1);
    expect(pops.find((p) => p.code.coding[0].code === "numerator")!.count).toBe(0);
  });

  it("existing terminology survives migration untouched", () => {
    const valuesets = [{ resourceType: "ValueSet", url: "urn:vs:1" }];
    const out = migrate({
      ...BASE_V5,
      schemaVersion: 4,
      terminology: { valuesets },
    });
    expect(out.terminology.valuesets).toEqual(valuesets);
  });

  it("library ids are positional for migrated state and unique for additions", () => {
    const libs = withLibraryIds([
      { name: "A", text: "library A" },
      { name: "B", text: "library B" },
    ]);
    expect(libs.map((l) => l.id)).toEqual(["lib_0", "lib_1"]);
    expect(newLibraryId(libs)).toBe("lib_2");
    expect(newLibraryId([...libs, { id: "lib_2", name: "C", text: "" }])).toBe("lib_3");
  });
});

describe("workspace zip v6 round-trip", () => {
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

  const V6_STATE = {
    libraries: [{ id: "lib_0", name: "L1", text: "library L1 version '1.0.0'" }],
    dataset: null,
    cases: null,
    prefs: {},
    measures: [{ id: "msr_0", mainLibraryId: "lib_0", resource: MEASURE }],
    activeMeasureId: "msr_0",
    expectedReports: {
      msr_0: [
        {
          resourceType: "MeasureReport",
          status: "complete",
          type: "individual",
          measure: "urn:cleanroom:measure",
          subject: { reference: "Patient/p1" },
          group: [
            {
              population: [
                { code: { coding: [{ code: "initial-population" }] }, count: 1 },
              ],
            },
          ],
        },
      ],
    },
    viewDefs: [],
    paramBindings: { msr_0: { P: "1" } },
    runHistory: [],
    activeTabPref: "cql",
    terminology: { valuesets: VS },
    viewConfig: null,
  };

  it("measures.json + expectedReports + viewdefs round-trip", () => {
    const bytes = exportWorkspaceZip({
      ...V6_STATE,
      viewDefs: [
        {
          id: "vd_0",
          name: "V",
          resource: { resource: "MeasureReport", select: [] },
        },
      ],
    } as never);
    const out = importWorkspaceZip(bytes);
    expect(out.measures).toHaveLength(1);
    expect(out.measures[0].resource).toEqual(MEASURE);
    expect(out.measures[0].mainLibraryId).toBe("lib_0");
    expect(out.activeMeasureId).toBe("msr_0");
    expect(out.expectedReports.msr_0).toEqual(V6_STATE.expectedReports.msr_0);
    expect(out.viewDefs).toHaveLength(1);
    expect(out.paramBindings).toEqual({ msr_0: { P: "1" } });
    expect(out.terminology.valuesets).toEqual(VS);
  });

  it("a null-resource measure entry (bootstrap mode) round-trips", () => {
    const bytes = exportWorkspaceZip({
      ...V6_STATE,
      measures: [{ id: "msr_0", mainLibraryId: "lib_0", resource: null }],
      expectedReports: {},
    } as never);
    const out = importWorkspaceZip(bytes);
    expect(out.measures).toHaveLength(1);
    expect(out.measures[0].id).toBe("msr_0");
    expect(out.measures[0].mainLibraryId).toBe("lib_0");
    expect(out.measures[0].resource).toBeNull();
  });

  it("a v5 zip (measure.json + paramValues) imports onto v6 fields", () => {
    // Hand-built v5 zip: workspace.json meta + measure.json + cases.json.
    const j = (o: unknown) =>
      new TextEncoder().encode(JSON.stringify(o));
    const bytes = zipSync({
      "workspace.json": j({
        schemaVersion: 5,
        format: "cql-cleanroom-workspace",
        libraries: [{ name: "L1", text: "library L1 version '1.0.0'" }],
        prefs: {},
        activeTabPref: "cql",
        paramValues: { P: "9" },
        viewConfig: null,
      }),
      "measure.json": j(MEASURE),
      "cases.json": j([
        { patient: "p1", population: "initial-population", expect: true },
      ]),
    });
    const out = importWorkspaceZip(bytes);
    expect(out.libraries[0].id).toBe("lib_0");
    expect(out.measures).toHaveLength(1);
    expect(out.measures[0].resource).toEqual(MEASURE);
    expect(out.measures[0].mainLibraryId).toBe("lib_0");
    expect(out.activeMeasureId).toBe("msr_0");
    expect(out.paramBindings.msr_0).toEqual({ P: "9" });
    expect(out.expectedReports.msr_0).toHaveLength(1);
    expect(out.cases).toHaveLength(1);
  });

  it("empty terminology omits valuesets.json; import still yields the default", () => {
    const bytes = exportWorkspaceZip({
      ...V6_STATE,
      terminology: { valuesets: [] },
    } as never);
    const out = importWorkspaceZip(bytes);
    expect(out.terminology).toEqual({ valuesets: [] });
  });

  it("non-array valuesets.json payload is ignored safely", () => {
    const bytes = exportWorkspaceZip({
      ...V6_STATE,
      terminology: { valuesets: [] },
    } as never);
    const out = importWorkspaceZip(bytes);
    expect(out.terminology).toEqual({ valuesets: [] });
  });

  it("runHistory never rides the zip (INV-4)", () => {
    const bytes = exportWorkspaceZip({
      ...V6_STATE,
      runHistory: [
        {
          id: "r1",
          name: "run",
          createdAt: 1,
          libraryHash: "h",
          datasetHash: "d",
          artifact: { patients: {} },
        },
      ],
    } as never);
    const out = importWorkspaceZip(bytes);
    expect(out.runHistory).toEqual([]);
  });
});
