import type { Page } from "@playwright/test";

/**
 * REORG 6f.1 — the `dataset-loaded` "Active: N resources" status line
 * was removed from the Tests pane. Specs wait on the tree itself now:
 * the total resource count is the sum of the per-patient count pills.
 */

export async function datasetResourceCount(page: Page): Promise<number> {
  return page.evaluate(() =>
    [...document.querySelectorAll(".dataset-patient-row .dataset-count-pill")].reduce(
      (sum, el) => sum + (Number(el.textContent) || 0),
      0,
    ),
  );
}

/** Wait until the Tests tree shows exactly `n` resources. */
export async function waitDatasetResources(
  page: Page,
  n: number,
  timeout = 30_000,
) {
  await page.waitForFunction(
    (target) =>
      [...document.querySelectorAll(".dataset-patient-row .dataset-count-pill")].reduce(
        (sum, el) => sum + (Number(el.textContent) || 0),
        0,
      ) === target,
    n,
    { timeout },
  );
}

/**
 * Replace the dataset with an in-memory collection Bundle via the
 * Import menu (the raw NDJSON view was retired in 6f.1).
 */
export async function importBundleResources(
  page: Page,
  resources: Array<Record<string, unknown>>,
) {
  await page.click("[data-testid=export-menu]");
  await page.click("[data-testid=bundle-mode]"); // merge -> replace
  await page.setInputFiles("[data-testid=bundle-import-input]", {
    name: "dataset.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({ resourceType: "Bundle", type: "collection", entry: resources.map((resource) => ({ resource })) }),
    ),
  });
}
