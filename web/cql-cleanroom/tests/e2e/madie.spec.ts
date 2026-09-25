import { expect, test } from "@playwright/test";
import { zipSync } from "fflate";
import * as fs from "node:fs";

/**
 * M2+M3 e2e: MADiE package import → evaluate → re-export round-trip.
 */

const enc = (s: string) => new TextEncoder().encode(s);

const MAIN_CQL = `library RoundTrip version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
valueset "Genders": 'urn:test:genders'

define "Initial Population":
  exists([Patient] P where P.gender in "Genders")

define "Has Name":
  exists([Patient] P where P.name.first().given.first() is not null)
`;

const MEASURE = {
  resourceType: "Measure",
  name: "RoundTrip",
  version: "1.0.0",
  status: "active",
  library: ["urn:cleanroom:lib:RoundTrip"],
  scoring: { coding: [{ system: "http://terminology.hl7.org/CodeSystem/measure-scoring", code: "proportion" }] },
  group: [
    {
      id: "group-1",
      population: [
        { code: { coding: [{ system: "http://terminology.hl7.org/CodeSystem/measure-population", code: "initial-population" }] }, criteria: { language: "text/cql-identifier", expression: "Initial Population" } },
        { code: { coding: [{ system: "http://terminology.hl7.org/CodeSystem/measure-population", code: "numerator" }] }, criteria: { language: "text/cql-identifier", expression: "Has Name" } },
      ],
    },
  ],
};

test("MADiE package import → evaluate → export round-trip", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  // IndexedDB persists across contexts (same origin): start clean so a
  // prior test's workspace can't restore over this import. Wait for the
  // reset's async defaults to LAND before reloading — an immediate
  // reload can race the click onto the new page (double reset).
  await page.click("[data-testid=workspace-reset]");
  await page.waitForFunction(
    () =>
      (document.querySelector("[data-testid=cql-editor]")?.textContent ?? "")
        .includes("CleanroomDemo"),
    undefined,
    { timeout: 30_000 },
  );
  await page.reload();
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  await page.click("[data-testid=workspace-reset]");

  // Write the package zip to disk, then drive the file input.
  const bytes = zipSync({
    "cql/RoundTrip-1.0.0.cql": enc(MAIN_CQL),
    "resources/measure-RoundTrip-1.0.0.json": enc(JSON.stringify(MEASURE, null, 2)),
  });
  const tmp = "/tmp/opencode/roundtrip-package.zip";
  fs.writeFileSync(tmp, bytes);
  await page.setInputFiles("[data-testid=madie-import-input]", tmp);
  await page.waitForFunction(
    () => document.querySelector(".status-note")?.textContent?.includes("imported measure package"),
    undefined,
    { timeout: 15_000 },
  );

  // The editor now shows the imported library (self-healing: the
  // Monaco-sync can lag the import by a render on slow first paint).
  await page.waitForFunction(
    () =>
      (document.querySelector("[data-testid=cql-editor]")?.textContent ?? "")
        .includes("RoundTrip"),
    undefined,
    { timeout: 30_000 },
  );

  // Load dataset + evaluate — Measure came from the package.
  await page.click("[data-testid=load-dataset]");
  await page.waitForSelector("[data-testid=dataset-loaded]");
  await page.waitForSelector("[data-testid=results-table]", { timeout: 90_000 });

  // MR tab renders the package's mapping.
  await page.click("[data-testid=results-tab-measure]");
  await page.waitForSelector("[data-testid=mr-table]", { timeout: 60_000 });

  // Export: capture the download.
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 30_000 }),
    (async () => {
      await page.click("[data-testid=export-menu]");
      await page.click("[data-testid=madie-export]");
    })(),
  ]);
  const out = "/tmp/opencode/roundtrip-export.zip";
  await download.saveAs(out);

  // Validate the export layout in-node.
  const outBytes = new Uint8Array(fs.readFileSync(out));
  const { unzipSync } = await import("fflate");
  const files = unzipSync(outBytes);
  const keys = Object.keys(files);
  if (!keys.some((k) => k === "cql/RoundTrip-1.0.0.cql")) throw new Error(`cql missing: ${keys}`);
  if (!keys.some((k) => k.includes("measure-RoundTrip"))) throw new Error(`measure missing: ${keys}`);
  if (!keys.some((k) => k.includes("library-RoundTrip"))) throw new Error(`library resource missing: ${keys}`);
  const exportedMeasure = JSON.parse(new TextDecoder().decode(files["resources/measure-RoundTrip-1.0.0.json"]));
  if (exportedMeasure.library[0] !== "urn:cleanroom:lib:RoundTrip") {
    throw new Error(`library[0]: ${exportedMeasure.library[0]}`);
  }
  expect(exportedMeasure.name).toBe("RoundTrip");
});
