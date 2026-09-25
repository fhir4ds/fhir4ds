import { test, type Page } from "@playwright/test";

/**
 * Test-data-authoring campaign e2e (FEATURE_CLEANROOM_TEST_DATA_AUTHORING.md):
 * dataset patient tree, builder v2 recursion (F8 at depth ≥2), Bundle
 * export/import, Results drawers + View overrides persistence.
 */

async function bootReady(page: Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
}

async function resetWorkspace(page: Page) {
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(1200);
}

test.describe("dataset patient tree", () => {
  test("groups demo resources by patient with flat-index rows", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.click("[data-testid=load-dataset]");
    await page.waitForSelector("[data-testid=dataset-loaded]", {
      timeout: 30_000,
    });

    // Tree view is the default: patient groups appear.
    await page.waitForSelector("[data-testid=dataset-tree]", {
      timeout: 10_000,
    });
    await page.waitForSelector("[data-testid=dataset-group-p1]");
    await page.waitForSelector("[data-testid=dataset-group-p2]");
    await page.waitForSelector("[data-testid=dataset-group-p3]");

    // Flat STORAGE-index row testids preserved (3 resources).
    await page.waitForSelector("[data-testid=dataset-row-0]");
    const rows = await page
      .locator("[data-testid^=dataset-row-]")
      .count();
    if (rows !== 3) throw new Error(`tree rows: ${rows}`);
  });

  test("raw view toggle keeps the legacy NDJSON editor", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.click("[data-testid=load-dataset]");
    await page.waitForSelector("[data-testid=dataset-loaded]", {
      timeout: 30_000,
    });
    await page.waitForSelector("[data-testid=dataset-tree]");
    await page.click("[data-testid=dataset-view-raw]");
    await page.waitForSelector("[data-testid=dataset-editor]", {
      timeout: 10_000,
    });
    await page.click("[data-testid=dataset-view-tree]");
    await page.waitForSelector("[data-testid=dataset-tree]");
  });
});

test.describe("builder v2 recursion", () => {
  test("nested HumanName + repeatable given array build a valid Patient", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);

    // Patient form: id + name (HumanName object) -> family + given[0..*].
    await page.fill("[data-testid=builder-field-id]", "p-tree-1");
    await page.click("[data-testid=builder-add-name]");
    await page.waitForSelector("[data-testid=builder-item-name-0]", {
      timeout: 10_000,
    });
    await page.fill("[data-testid=builder-field-family]", "Roe");
    await page.click("[data-testid=builder-add-given]");
    await page.fill("[data-testid=builder-field-given-0]", "Mary");
    await page.click("[data-testid=builder-add-given]");
    await page.fill("[data-testid=builder-field-given-1]", "Jane");

    await page.click("[data-testid=builder-validate]");
    await page.waitForSelector("[data-testid=builder-valid]", {
      timeout: 30_000,
    });

    // Add to dataset: the F8 chain (green form => loads).
    await page.click("[data-testid=builder-add]");
    await page.waitForSelector("[data-testid=dataset-loaded]", {
      timeout: 10_000,
    });

    // The new patient appears as its own tree group.
    await page.waitForSelector("[data-testid=dataset-group-p-tree-1]", {
      timeout: 10_000,
    });
  });

  test("reference picker emits Reference objects with context default", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.click("[data-testid=load-dataset]");
    await page.waitForSelector("[data-testid=dataset-loaded]");

    // Per-patient + on p1: opens the builder for a new resource with
    // a subject-class field preseeded to Patient/p1 (Observation has
    // no subject-class field at top level in the demo SD — Condition
    // does). Use Condition.
    await page.click("[data-testid=dataset-add-p1]");
    await page.selectOption("[data-testid=builder-type]", "Condition");
    await page.fill("[data-testid=builder-field-id]", "cond-p1-1");
    await page.click("[data-testid=builder-validate]");
    await page.waitForSelector("[data-testid=builder-valid]", {
      timeout: 30_000,
    });
    await page.click("[data-testid=builder-add]");
    await page.waitForSelector("[data-testid=dataset-loaded]");

    // The condition lands INSIDE p1's group (subject preseed).
    const groupText = await page.textContent(
      "[data-testid=dataset-group-p1]",
    );
    if (!groupText?.includes("Condition")) {
      throw new Error(`condition not grouped under p1: ${groupText}`);
    }
  });
});

test.describe("bundle export/import", () => {
  test("export then replace-import round-trips the dataset", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.click("[data-testid=load-dataset]");
    await page.waitForSelector("[data-testid=dataset-loaded]");

    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 60_000 }),
      (async () => {
        await page.click("[data-testid=export-menu]");
        await page.click("[data-testid=bundle-export]");
      })(),
    ]);
    const path = await download.path();
    if (!path) throw new Error("no download path");

    // Wipe + re-import in replace mode (click-toggle button).
    await page.click("[data-testid=workspace-reset]");
    await page.waitForTimeout(1200);
    await page.click("[data-testid=bundle-mode]"); // merge -> replace
    await page.setInputFiles("[data-testid=bundle-import-input]", path);
    await page.waitForSelector("[data-testid=dataset-loaded]", {
      timeout: 30_000,
    });
    const loaded = await page.textContent("[data-testid=dataset-loaded]");
    if (!loaded?.includes("3")) throw new Error(`dataset not restored: ${loaded}`);
  });
});

test.describe("results drawers", () => {
  test("populations + view tabs render their panes and toggle", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);

    // Measure pane lives in the MeasureReport tab.
    await page.click("[data-testid=results-tab-measure]");
    await page.waitForSelector("[data-testid=measure-pane]", {
      timeout: 10_000,
    });

    // View pane lives in the View tab; tab panels stay mounted, so
    // leaving HIDES the pane (detached no longer applies).
    await page.click("[data-testid=results-tab-view]");
    await page.waitForSelector("[data-testid=view-pane]", {
      timeout: 10_000,
    });
    await page.click("[data-testid=results-tab-cql]");
    await page.waitForSelector("[data-testid=view-pane]", {
      state: "hidden",
      timeout: 10_000,
    });
    await page.click("[data-testid=results-tab-view]");
    await page.waitForSelector("[data-testid=view-pane]");
  });
});
