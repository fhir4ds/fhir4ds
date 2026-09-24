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

  // Evidence lives in the CQL tab drawer — it starts OPEN; only
  // click the toggle when the <details> is actually closed.
  const evOpen = await page.evaluate(
    () =>
      (document.querySelector(
        "[data-testid=drawer-evidence] details",
      ) as HTMLDetailsElement | null)?.open ?? false,
  );
  if (!evOpen) {
    await page.click("[data-testid=drawer-evidence-toggle]");
  }

  // Explain p1: IPP population badge + evidence rows (patient picker —
  // dataset is loaded so the input renders as a <select>).
  await page.selectOption("[data-testid=evidence-patient-input]", {
    label: "p1 — Ann",
  });
  await page.click("[data-testid=explain-btn]");
  await page.waitForSelector("[data-testid=evidence-body]", {
    timeout: 60_000,
  });
  const ipp = await page.textContent("[data-testid=ev-pop-initial_population]");
  if (!ipp?.includes("true")) throw new Error(`IPP: ${ipp}`);
  const defs = await page.locator("[data-testid^=ev-def-]").count();
  if (defs < 1) throw new Error("no evidence definitions rendered");

  // Population flow (Sankey): rendered in the MeasureReport tab after
  // an evaluation — initial_population node with count 2.
  await page.click("[data-testid=run-eval]");
  await page.waitForSelector("[data-testid=results-table]", {
    timeout: 60_000,
  });
  await page.click("[data-testid=results-tab-measure]");
  await page.waitForSelector("[data-testid=population-sankey]", {
    timeout: 60_000,
  });
  const ippNode = await page.textContent(
    "[data-testid=sankey-node-initial_population]",
  );
  if (!ippNode?.includes("(2)")) throw new Error(`sankey IPP: ${ippNode}`);
});

test("fhirpath playground evaluates dataset resource via picker", async ({
  page,
}) => {
  await bootReady(page);
  // Dataset first so the picker has resources; then open the drawer.
  await page.click("[data-testid=load-dataset]");
  await page.waitForSelector("[data-testid=dataset-loaded]", {
    timeout: 30_000,
  });
  await page.click("[data-testid=drawer-fhirpath-toggle]");
  await page.selectOption("[data-testid=fp-resource-select]", {
    label: "p1",
  });
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
