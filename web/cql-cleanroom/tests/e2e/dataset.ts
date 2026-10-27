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
 * Test Cases section menu (S32: File > Open > FHIR Bundle moved to
 * nav Tests ▾ "Import Bundle .json…" — merge mode).
 */
export async function importBundleResources(
  page: Page,
  resources: Array<Record<string, unknown>>,
) {
  // The Tests drawer must be open for the section menu.
  const tree = page.locator('[data-testid="dataset-tree"]');
  if (!(await tree.isVisible().catch(() => false))) {
    await page.click('[data-testid="nav-toggle-tests"]');
    await page.waitForTimeout(500);
  }
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser", { timeout: 15_000 }),
    (async () => {
      await page.click("[data-testid=nav-import-tests]");
      await page.click("[data-testid=nav-import-tests-bundle-json]");
    })(),
  ]);
  await chooser.setFiles({
    name: "dataset.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({ resourceType: "Bundle", type: "collection", entry: resources.map((resource) => ({ resource })) }),
    ),
  });
}
