import { test, expect, type Page } from "@playwright/test";

/**
 * C1-U3/U4 capability round-trips through the live cleanroom worker.
 *
 * ONE page + ONE worker for the whole serial group: each Pyodide boot is
 * 40-60s; per-test boots would multiply the suite by 7 and risk OOM.
 */

test.describe.serial("cleanroom capabilities", () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto("/");
    // The app's own singleton worker boots with the page; wait for it.
    await page.waitForFunction(() => (window as any).__cleanroom !== undefined);
    await page.waitForSelector(".version-badge", { timeout: 120_000 });
  });

  test.afterAll(async () => {
    await page.close();
  });

  const MAIN_LIB = {
    name: "Simple",
    text: `library Simple version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
define "Initial Population":
  exists([Patient] P where P.gender = 'female')
define "Has Name":
  exists([Patient] P where P.name.first().given.first() is not null)
`,
  };

  const PATIENTS = [
    { resourceType: "Patient", id: "p1", gender: "female", name: [{ given: ["Ann"] }] },
    { resourceType: "Patient", id: "p2", gender: "male", name: [{ given: ["Bob"] }] },
    { resourceType: "Patient", id: "p3", gender: "female" },
  ];

  test("parse_cql envelope", async () => {
    const resp = await page.evaluate(
      (text) => (window as any).__cleanroom({ type: "parse_cql", text }),
      MAIN_LIB.text,
    );
    expect(resp.ok).toBe(true);
    const env = JSON.parse(resp.envelope);
    expect(env.schema).toBe(1);
    expect(env.ok).toBe(true);
    expect(env.library_name).toBe("Simple");
    expect(env.definition_names).toContain("Initial Population");
  });

  test("translate_cql envelope with column_types", async () => {
    const resp = await page.evaluate(
      (libraries) =>
        (window as any).__cleanroom({
          type: "translate_cql",
          libraries,
          main: libraries[0],
        }),
      [MAIN_LIB],
    );
    const env = JSON.parse(resp.envelope);
    expect(env.ok).toBe(true);
    expect(env.sql.toUpperCase()).toContain("WITH");
    expect(env.column_types["Initial Population"]).toBe("Boolean");
    expect(env.definitions).toEqual(
      expect.arrayContaining(["Initial Population", "Has Name"]),
    );
  });

  test("validate_resource round-trip", async () => {
    const okResp = await page.evaluate(
      (resource) =>
        (window as any).__cleanroom({ type: "validate_resource", resource }),
      { resourceType: "Patient", id: "p1" },
    );
    const okEnv = JSON.parse(okResp.envelope);
    expect(okEnv.valid).toBe(true);
    expect(okEnv.resource_type).toBe("Patient");

    const badResp = await page.evaluate(
      (resource) =>
        (window as any).__cleanroom({ type: "validate_resource", resource }),
      { resourceType: "Patient", id: "bad id!" },
    );
    const badEnv = JSON.parse(badResp.envelope);
    expect(badEnv.valid).toBe(false);
    expect(badEnv.diagnostics[0].code).toBe("input_error");
  });

  test("resource_schema round-trip", async () => {
    const resp = await page.evaluate(
      (resource_type) =>
        (window as any).__cleanroom({ type: "resource_schema", resource_type }),
      "Patient",
    );
    const env = JSON.parse(resp.envelope);
    expect(env.ok).toBe(true);
    const gp = env.fields.find((f: any) => f.name === "generalPractitioner");
    expect(gp.types).toEqual(["Reference"]);
    expect(gp.reference_targets).toContain("Organization");

    const nf = await page.evaluate(
      (resource_type) =>
        (window as any).__cleanroom({ type: "resource_schema", resource_type }),
      "Bogus",
    );
    const nfEnv = JSON.parse(nf.envelope);
    expect(nfEnv.ok).toBe(false);
    expect(nfEnv.diagnostics[0].code).toBe("not_found");
  });

  test("evaluate_library executes on duckdb-wasm", async () => {
    const resp = await page.evaluate(
      ({ libraries, dataset }) =>
        (window as any).__cleanroom({
          type: "evaluate_library",
          libraries,
          main: libraries[0],
          dataset,
          output_columns: { IPP: "Initial Population", NAME: "Has Name" },
        }),
      { libraries: [MAIN_LIB], dataset: { resources: PATIENTS } },
    );
    const env = JSON.parse(resp.envelope);
    expect(env.ok).toBe(true);
    expect(env.patient_count).toBe(3);
    const byId: Record<string, any> = {};
    for (const row of env.rows) byId[row.patient_id] = row;
    expect(byId.p1.IPP).toBe(true);
    expect(byId.p2.IPP).toBe(false);
    expect(byId.p3.NAME).toBe(false);
    expect(env.column_types.IPP).toBe("Boolean");
  });

  test("run_tests envelope parity", async () => {
    const resp = await page.evaluate(
      ({ libraries, dataset }) =>
        (window as any).__cleanroom({
          type: "run_tests",
          libraries,
          main: libraries[0],
          dataset,
          tests: {
            schema: 1,
            cases: [
              { patient: "p1", population: "Initial Population", expect: true },
              { patient: "p2", population: "Initial Population", expect: false },
              { patient: "zz", population: "Initial Population", expect: true },
            ],
          },
        }),
      { libraries: [MAIN_LIB], dataset: { resources: PATIENTS } },
    );
    const env = JSON.parse(resp.envelope);
    expect(env.ok).toBe(true);
    expect(env.passed).toBe(false);
    expect(env.tests.total).toBe(3);
    expect(env.tests.passed).toBe(2);
    expect(env.tests.failures[0].patient).toBe("zz");
    expect(env.tests.failures[0].reason).toContain("unknown patient");
  });

  test("explain_patient envelope parity", async () => {
    const resp = await page.evaluate(
      ({ libraries, dataset }) =>
        (window as any).__cleanroom({
          type: "explain_patient",
          libraries,
          main: libraries[0],
          dataset,
          patient_id: "p1",
          output_columns: { IPP: "Initial Population" },
        }),
      { libraries: [MAIN_LIB], dataset: { resources: PATIENTS } },
    );
    const env = JSON.parse(resp.envelope);
    expect(env.ok).toBe(true);
    expect(env.patient_id).toBe("p1");
    expect(env.populations.IPP).toBe(true);
    expect(Array.isArray(env.definitions)).toBe(true);
  });
});
