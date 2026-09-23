import { test, type Page } from "@playwright/test";

/**
 * C1-U7 e2e: workspace persistence (IndexedDB), multi-library tabs,
 * evidence drill-in + population flow, FHIRPath playground.
 */

async function bootReady(page: Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
}

test("workspace persists libraries and dataset across reload", async ({ page }) => {
  await bootReady(page);

  // Load dataset + add a second library tab
  await page.click("[data-testid=load-dataset]");
  await page.waitForSelector("[data-testid=dataset-loaded]");
  await page.click("[data-testid=library-tab-add]");
  await page.waitForSelector("[data-testid=library-tab-1]");

  // Autosave debounce (800ms) + IndexedDB write
  await page.waitForTimeout(2000);

  // Reload: tabs + dataset restored
  await page.reload();
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForSelector("[data-testid=library-tab-1]", { timeout: 30_000 });
  await page.waitForSelector("[data-testid=dataset-loaded]", {
    timeout: 30_000,
  });
  const loaded = await page.textContent("[data-testid=dataset-loaded]");
  if (!loaded?.includes("3")) throw new Error(`dataset not restored: ${loaded}`);

  // Reset to defaults so other tests are unaffected
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(1200);
});

test("evidence drill-in and population flow", async ({ page }) => {
  await bootReady(page);
  await page.click("[data-testid=load-dataset]");
  await page.waitForSelector("[data-testid=dataset-loaded]");

  // Explain p1: IPP population badge + evidence rows
  await page.fill("[data-testid=evidence-patient-input]", "p1");
  await page.click("[data-testid=explain-btn]");
  await page.waitForSelector("[data-testid=evidence-body]", {
    timeout: 60_000,
  });
  const ipp = await page.textContent("[data-testid=ev-pop-IPP]");
  if (!ipp?.includes("true")) throw new Error(`IPP: ${ipp}`);
  const defs = await page.locator("[data-testid^=ev-def-]").count();
  if (defs < 1) throw new Error("no evidence definitions rendered");

  // Population flow (Sankey): IPP node with count 2
  await page.click("[data-testid=sankey-btn]");
  await page.waitForSelector("[data-testid=population-sankey]", {
    timeout: 60_000,
  });
  const ippNode = await page.textContent(
    "[data-testid=sankey-node-IPP]",
  );
  if (!ippNode?.includes("(2)")) throw new Error(`sankey IPP: ${ippNode}`);
});

test("fhirpath playground evaluates against pasted resource", async ({
  page,
}) => {
  await bootReady(page);
  await page.fill("[data-testid=fp-expr]", "name.given.first()");
  await page.click("[data-testid=fp-run]");
  await page.waitForFunction(
    () =>
      (document.querySelector("[data-testid=fp-result]") as HTMLElement)
        ?.textContent &&
      (document.querySelector("[data-testid=fp-result]") as HTMLElement)!
        .textContent!
        .includes("Ann"),
    undefined,
    { timeout: 30_000 },
  );
});
