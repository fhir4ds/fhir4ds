import { test, type Page } from "@playwright/test";
import { waitDatasetResources } from "./dataset";

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
  // Deterministic start: prior specs' auto-commits persist (same
  // origin). Reset restores the 3-resource demo synchronously; wait
  // for the count AND the autosave flush before reloading.
  await page.click("[data-testid=workspace-reset]");
  await waitDatasetResources(page, 3, 10_000);
  await page.waitForTimeout(1500);

  // Load dataset + add a second library tab
  await page.waitForSelector("[data-testid=dataset-tree]");
  await page.click("[data-testid=nav-toggle-libraries]");
  await page.click("[data-testid=library-tab-add]");
  await page.waitForSelector("[data-testid=library-tab-1]");

  // Autosave debounce (800ms) + IndexedDB write
  await page.waitForTimeout(2000);

  // Reload: tabs + dataset restored (panel defaults back to Tests;
  // read the boot signal, then reopen Libraries to see the restored
  // tabs — REORG 6d).
  await page.reload();
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await waitDatasetResources(page, 3, 30_000);
  await page.click("[data-testid=nav-toggle-libraries]");
  await page.waitForSelector("[data-testid=library-tab-1]", { timeout: 30_000 });

  // Reset to defaults so other tests are unaffected
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(1200);
});

test("cell evidence drill-in and population flow", async ({ page }) => {
  await bootReady(page);
  await page.waitForSelector("[data-testid=dataset-tree]");

  // Auto-evaluation runs (no Evaluate button) — wait for results.
  await page.waitForSelector("[data-testid=results-table]", {
    timeout: 90_000,
  });

  // Evidence drill-in is now the CELL POPOVER: click p1's IPP cell.
  await page.click('[data-testid="cell-p1-initial_population"]');
  await page.waitForSelector("[data-testid=evidence-popover]", {
    timeout: 60_000,
  });
  await page.waitForSelector("[data-testid=evidence-verdict]", {
    timeout: 60_000,
  });
  const ipp = await page.textContent("[data-testid=evidence-verdict]");
  if (!ipp?.includes("true")) throw new Error(`IPP verdict: ${ipp}`);
  const rows = await page.locator("[data-testid^=evidence-row-]").count();
  if (rows < 1) throw new Error("no evidence rows rendered");

  // Population flow (Sankey): the console's Funnel tab while a measure
  // editor tab is active (REORG 6e) — initial_population node with
  // count 2.
  await page.click("[data-testid=nav-toggle-measures]");
  await page.locator("[data-testid^=nav-item-measure-]").first().click();
  await page.click("[data-testid=console-tab-funnel]");
  await page.waitForSelector("[data-testid=population-sankey]", {
    timeout: 90_000,
  });
  const ippNode = await page.textContent(
    "[data-testid=sankey-node-initial_population]",
  );
  if (!ippNode?.includes("(2)")) throw new Error(`sankey IPP: ${ippNode}`);
});

// The FHIRPath scratchpad retired in WORKBENCH_REORG phase 4 — its
// coverage lives in console.spec.ts (CQL console Run-Selection).
