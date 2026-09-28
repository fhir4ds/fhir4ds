import { expect, test } from "@playwright/test";
import { importBundleResources, waitDatasetResources } from "./dataset";

/**
 * PASS2 e2e: nav rail (G1) + terminology pane (G2).
 */

async function bootReady(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}

async function resetWorkspace(page: import("@playwright/test").Page) {
  await page.click("[data-testid=workspace-reset]");
  await page.reload();
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
}

test.describe("nav rail", () => {
  test("rail replaces the tab-strip; library testids live in the rail", async ({ page }) => {
    await bootReady(page);
    await expect(page.locator("[data-testid=nav-rail]")).toBeVisible();
    // REORG 6d: one nav panel at a time — open Libraries.
    await page.click("[data-testid=nav-toggle-libraries]");
    await expect(page.locator("[data-testid=nav-rail] [data-testid=library-tab-0]")).toBeVisible();
    await expect(page.locator("[data-testid=nav-rail] [data-testid=library-tab-add]")).toBeVisible();
    // The RESULTS tab strip stays; the LIBRARY tab-strip container
    // testid now lives (hidden alias) inside the rail.
    await expect(page.locator("main > .pane-col .tab-strip[data-testid=library-tabs]")).toHaveCount(0);
  });

  test("entrypoint marker defaults to the first library; dbl-click moves it", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.click("[data-testid=nav-toggle-libraries]");
    await page.click("[data-testid=library-tab-add]");
    await page.waitForSelector("[data-testid=library-tab-1]");
    // entrypoint badge is on library 0 by default
    await expect(page.locator("[data-testid=library-tab-0] .rail-badge.entry")).toBeVisible();
    // dbl-click library 1 → entrypoint moves
    await page.dblclick("[data-testid=library-tab-1]");
    await expect(page.locator("[data-testid=library-tab-1] .rail-badge.entry")).toBeVisible();
    await expect(page.locator("[data-testid=library-tab-0] .rail-badge.entry")).toHaveCount(0);
  });

  test("evaluation uses the ENTRYPOINT library, not the edited tab", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.waitForSelector("[data-testid=dataset-tree]");

    // Add a second library whose IPP differs (male instead of female).
    await page.click("[data-testid=nav-toggle-libraries]");
    await page.click("[data-testid=library-tab-add]");
    await page.waitForSelector("[data-testid=library-tab-1]");
    await page.click("[data-testid=library-tab-1]");
    await page.click("[data-testid=cql-editor]");
    await page.keyboard.press("Control+Home");
    await page.keyboard.press("Control+Shift+End");
    await page.keyboard.insertText(
      `library Library2 version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers

define "Initial Population":
  exists([Patient] P where P.gender = 'male')

define "Has Name":
  exists([Patient] P where P.name.first().given.first() is not null)
`,
    );

    // Entry stays on library 0 (female): running evaluates library 0.
    await page.waitForSelector("[data-testid=results-table]", { timeout: 90_000 });
    // demo truths: p1 female T, p2 male F, p3 female T → 2 true
    const cell = await page.textContent("[data-testid=results-table] tbody tr td:nth-child(2)");
    if (!cell?.includes("true")) throw new Error(`p1 IPP under entrypoint lib0: ${cell}`);

    // Move entrypoint to library 2 (male) WITHOUT editing: p1 flips false.
    // (results-table never detaches — wait on the cell VALUE flipping.)
    await page.dblclick("[data-testid=library-tab-1]");
    await page.waitForFunction(
      () =>
        (document.querySelector(
          "[data-testid=results-table] tbody tr td:nth-child(2)",
        )?.textContent ?? "").includes("false"),
      undefined,
      { timeout: 90_000 },
    );
    const cell2 = await page.textContent("[data-testid=results-table] tbody tr td:nth-child(2)");
    if (!cell2?.includes("false")) throw new Error(`p1 IPP under entrypoint lib1: ${cell2}`);
  });

  test("parse-error badge appears on a broken library", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.click("[data-testid=nav-toggle-libraries]");
    await page.click("[data-testid=library-tab-add]");
    await page.waitForSelector("[data-testid=library-tab-1]");
    await page.click("[data-testid=library-tab-1]");
    await page.click("[data-testid=cql-editor]");
    await page.keyboard.press("Control+Home");
    await page.keyboard.press("Control+Shift+End");
    await page.keyboard.insertText("this is not cql at all {{{");
    await page.waitForSelector("[data-testid=library-tab-1] .rail-badge.err", {
      timeout: 30_000,
    });
  });
});

test.describe("valuesets", () => {
  test("workspace ValueSet seeds the engine cache and affects evaluation", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);

    // Library declares a valueset used over a Coding path (in_valueset
    // extracts systems from Coding objects; bare primitives like gender
    // carry no system and never match — engine semantics). Edit the
    // library FIRST: opening the valueset editor tab hides it.
    await page.click("[data-testid=cql-editor]");
    await page.keyboard.press("Control+Home");
    await page.keyboard.press("Control+Shift+End");
    await page.keyboard.insertText(
      `library CleanroomDemo version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
valueset "Vitals": 'urn:cleanroom:test:vitals'

define "Initial Population":
  exists([Observation] O where O.code in "Vitals")

define "Has Name":
  exists([Patient] P where P.name.first().given.first() is not null)
`,
    );

    // Create a workspace valueset via the rail section "+" (6h: the
    // terminology pane is gone) and give it the url the library declares.
    await page.click("[data-testid=nav-toggle-valuesets]");
    await page.click("[data-testid=nav-add-valuesets]");
    await page.waitForSelector("[data-testid=valueset-editor]", { timeout: 30_000 });
    await page.fill("[data-testid=valueset-url]", "urn:cleanroom:test:vitals");

    // The dataset count pills live in the Tests panel — switch the nav
    // panel back (the valueset stays open as an EDITOR tab).
    await page.click("[data-testid=nav-toggle-tests]");

    // Dataset: one BP observation (LOINC 8480-6) + patients for attribution.
    // REORG 6f.1: import via the menu (the raw NDJSON view is gone).
    await importBundleResources(page, [
      { resourceType: "Patient", id: "p1", gender: "female", name: [{ given: ["Ann"] }] },
      { resourceType: "Observation", id: "bp1", status: "final", code: { coding: [{ system: "http://loinc.org", code: "8480-6" }] }, subject: { reference: "Patient/p1" } },
    ]);
    await waitDatasetResources(page, 2, 30_000);

    // Evaluate BEFORE adding codes: p1 not in the empty VS → false.
    // The auto-eval may still show the pre-edit demo result (p1=true)
    // — wait until the SETTLED result reflects the edited library
    // (empty VS membership → false), polling the cell.
    await page.waitForFunction(
      () =>
        (document.querySelector(
          "[data-testid=results-table] tbody tr td:nth-child(2)",
        )?.textContent ?? "").includes("false"),
      undefined,
      { timeout: 120_000 },
    );
    const before = await page.textContent("[data-testid=results-table] tbody tr td:nth-child(2)");
    if (!before?.includes("false")) throw new Error(`p1 IPP before codes: ${before}`);

    // Add the LOINC BP code to the workspace valueset.
    await page.locator("[data-testid^=editor-tab-valueset-]").first().click();
    await page.click("[data-testid=valueset-add-code]");
    await page.fill("[data-testid=valueset-codes] input[aria-label=system]", "http://loinc.org");
    await page.fill("[data-testid=valueset-codes] input[aria-label=code]", "8480-6");

    // Evaluate again: the Observation code is now in the VS → true.
    // (results-table never detaches — wait on the cell VALUE flipping.)
    await page.waitForFunction(
      () =>
        (document.querySelector(
          "[data-testid=results-table] tbody tr td:nth-child(2)",
        )?.textContent ?? "").includes("true"),
      undefined,
      { timeout: 90_000 },
    );
    const after = await page.textContent("[data-testid=results-table] tbody tr td:nth-child(2)");
    if (!after?.includes("true")) throw new Error(`p1 IPP after codes: ${after}`);
  });

  test("workspace valuesets persist across reload", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.click("[data-testid=nav-toggle-valuesets]");
    await page.click("[data-testid=nav-add-valuesets]");
    await page.waitForSelector("[data-testid=valueset-editor]", { timeout: 30_000 });
    await page.fill("[data-testid=valueset-url]", "urn:cleanroom:test:vitals");
    await page.click("[data-testid=valueset-add-code]");
    await page.fill("[data-testid=valueset-codes] input[aria-label=system]", "urn:s");
    await page.fill("[data-testid=valueset-codes] input[aria-label=code]", "c1");
    await page.waitForTimeout(1200); // debounce autosave
    await page.reload();
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await page.click("[data-testid=nav-toggle-valuesets]");
    // rowTestId prepends the kind to the TabId (valueset:ws:<url>) —
    // the ws marker lands twice.
    await page.waitForSelector("[data-testid^=nav-item-valueset-valueset-ws-]", { timeout: 30_000 });
  });
});
